"""Sentiment analysis interface and implementations."""
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod

from ..common.clock import utcnow
from ..common.events import NewsEvent, SentimentEvent
from ..common.retry import retry

logger = logging.getLogger(__name__)


class BaseSentimentAnalyzer(ABC):
    """Interface for sentiment analyzers. Swap implementations freely."""

    @abstractmethod
    def analyze(self, event: NewsEvent, positions: dict = None) -> SentimentEvent:
        pass


# --- Keyword-based (fast, free, no deps) ---

TICKER_MAP = {
    "apple": "AAPL", "aapl": "AAPL",
    "microsoft": "MSFT", "msft": "MSFT",
    "google": "GOOGL", "alphabet": "GOOGL", "googl": "GOOGL",
    "amazon": "AMZN", "amzn": "AMZN",
    "tesla": "TSLA", "tsla": "TSLA",
    "nvidia": "NVDA", "nvda": "NVDA",
    "meta": "META", "facebook": "META",
    "netflix": "NFLX", "nflx": "NFLX",
    "boeing": "BA",
    "jpmorgan": "JPM", "jp morgan": "JPM",
    "goldman": "GS", "goldman sachs": "GS",
}

SECTOR_KEYWORDS = {
    "technology": ["tech", "chip", "semiconductor", "software", "ai ", "artificial intelligence"],
    "energy": ["oil", "gas", "energy", "opec", "petroleum"],
    "finance": ["bank", "financial", "interest rate", "fed ", "federal reserve"],
    "healthcare": ["pharma", "drug", "fda", "healthcare", "biotech"],
    "consumer": ["retail", "consumer", "shopping"],
}

BULLISH_WORDS = [
    "surge", "soar", "rally", "jump", "gain", "rise", "beat", "exceed",
    "upgrade", "bullish", "record high", "boom", "strong", "growth",
    "profit", "positive", "optimistic", "deal", "partnership",
]
BEARISH_WORDS = [
    "crash", "plunge", "drop", "fall", "decline", "miss", "cut",
    "downgrade", "bearish", "record low", "bust", "weak", "loss",
    "negative", "pessimistic", "tariff", "sanction", "ban", "war",
    "recession", "layoff", "bankruptcy", "default", "investigation",
]


class KeywordSentimentAnalyzer(BaseSentimentAnalyzer):
    """Fast keyword-based scorer. No external dependencies."""

    def analyze(self, event: NewsEvent, positions: dict = None) -> SentimentEvent:
        t0 = time.perf_counter()
        text = (event.headline + " " + event.body).lower()

        symbols = []
        for keyword, ticker in TICKER_MAP.items():
            if keyword in text and ticker not in symbols:
                symbols.append(ticker)

        sector = ""
        for sec, keywords in SECTOR_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                sector = sec
                break

        bull = sum(1 for w in BULLISH_WORDS if w in text)
        bear = sum(1 for w in BEARISH_WORDS if w in text)
        total = bull + bear
        if total == 0:
            sentiment, confidence = 0.0, 0.0
        else:
            sentiment = (bull - bear) / total
            confidence = min(total / 5, 1.0)

        urgency = "high" if any(w in text for w in ["crash", "surge", "ban", "war", "tariff"]) else "normal"
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info("Keyword analysis in %.1fms — sentiment=%+.2f confidence=%.2f symbols=%s",
                     elapsed_ms, round(sentiment, 3), round(confidence, 3), symbols)

        return SentimentEvent(
            source=event.source, headline=event.headline,
            timestamp=event.timestamp,
            analyzed_at=utcnow().isoformat() + "Z",
            symbols=symbols, sector=sector,
            sentiment=round(sentiment, 3),
            confidence=round(confidence, 3),
            urgency=urgency,
        )


# --- LLM-based (accurate, needs API key) ---

_LLM_COMMON_RULES = """\
- We trade CASH ONLY — no margin, no short selling, no borrowing.
- We can only trade stocks on these markets: {markets}
- Only return symbols that are well-known, actively traded stocks with a valid Yahoo Finance ticker. For example: 00700.HK (Tencent), 9988.HK (Alibaba HK), 00005.HK (HSBC HK), 0388.HK (HKEX).
- HK tickers MUST be 4 digits with leading zeros: 0883.HK is valid, 883.HK is NOT. 0981.HK is valid, 981.HK is NOT.
- Do NOT return US tickers like AAPL, TSLA, NVDA unless we can trade US stocks.
- Always try to find indirect links to Hong Kong stocks, even if the news is not directly about HK. For example: negative US tech news (e.g. chip restrictions, AI regulation, big tech earnings miss) may also impact HK-listed tech stocks like Tencent, Alibaba, or Semiconductor Manufacturing International (0981.HK). News about US-China trade tensions, tariffs, or sanctions directly affects HK stocks. Global macro events (Fed decisions, oil prices, recession fears) have spillover effects on HK markets.
- When you identify an indirect link, use lower confidence (0.3-0.6) to reflect the indirect nature of the connection. Use higher confidence (0.7-1.0) only for direct mentions.
- Even if the news mentions only US or global events, if there is a plausible connection to HK stocks, return those HK tickers with appropriate sentiment and confidence.
- Only return empty symbols if there is truly no meaningful connection to any HK stock.
- Sentiment is from the perspective of the returned symbols (positive = those symbols go up)."""

_LLM_POSITION_EXTRA = """\
If we hold a stock and the news is bad for it (directly or indirectly), return that stock with negative sentiment so we sell it.
- Higher confidence if the news directly impacts our holdings."""

_LLM_RETURN_EXAMPLE = """
Return:
{{
  "symbols": ["00700.HK"],
  "sector": "technology",
  "sentiment": 0.5,
  "confidence": 0.8,
  "urgency": "normal"
}}"""


def _build_llm_prompt(headline: str, markets: str, positions: dict = None) -> str:
    parts = ["Analyze this financial news headline" +
             (" considering the current portfolio" if positions else "") +
             ". Return JSON only, no explanation.",
             f'\nHeadline: "{headline}"']
    if positions:
        pos_str = "\n".join(f"- {sym}" for sym in positions.keys()) or "None"
        parts.append(f"\nCurrent holdings:\n{pos_str}")
    parts.append("\nRules:")
    parts.append(_LLM_COMMON_RULES.format(markets=markets))
    if positions:
        parts.append(_LLM_POSITION_EXTRA)
    parts.append(_LLM_RETURN_EXAMPLE)
    return "\n".join(parts)


class LLMSentimentAnalyzer(BaseSentimentAnalyzer):
    """LLM-based scorer. More accurate, needs API key.

    Supports any OpenAI-compatible API (OpenAI, Azure, opencode Zen, Ollama, local LLMs).
    Set OPENCODE_API_KEY to use opencode Zen (free big-pickle model by default).
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
    ):
        opencode_key = api_key or os.getenv("OPENCODE_API_KEY")
        if opencode_key:
            self.api_key = opencode_key
            self.base_url = base_url or os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1")
            self.model = model or os.getenv("OPENCODE_MODEL", "big-pickle")
        else:
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def _get_client(self):
        from openai import OpenAI
        return OpenAI(base_url=self.base_url, api_key=self.api_key)

    def analyze(self, event: NewsEvent, positions: dict = None) -> SentimentEvent:
        from src.settings import settings

        prompt = _build_llm_prompt(event.headline, settings.tradable_markets, positions)
        t0 = time.perf_counter()
        try:
            content = self._call_llm(prompt)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            # Extract JSON from response (handle markdown code blocks)
            content = re.sub(r"```json?\s*", "", content).replace("```", "").strip()
            data = json.loads(content)

            logger.info("LLM response in %.0fms — sentiment=%+.2f confidence=%.2f symbols=%s",
                        elapsed_ms, float(data.get("sentiment", 0)),
                        float(data.get("confidence", 0)), data.get("symbols", []))

            return SentimentEvent(
                source=event.source, headline=event.headline,
                timestamp=event.timestamp,
                analyzed_at=utcnow().isoformat() + "Z",
                symbols=data.get("symbols", []),
                sector=data.get("sector", ""),
                sentiment=round(float(data.get("sentiment", 0)), 3),
                confidence=round(float(data.get("confidence", 0)), 3),
                urgency=data.get("urgency", "normal"),
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.error("LLM analysis failed after %.0fms: %s", elapsed_ms, e)
            raise

    @retry(max_attempts=3, base_delay=1.0, exceptions=(Exception,))
    def _call_llm(self, prompt: str) -> str:
        client = self._get_client()
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content
