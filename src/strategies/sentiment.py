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


def _parse_llm_json(text: str) -> dict:
    """Parse a JSON object from an LLM response, tolerating prose, fences, and double braces."""
    text = re.sub(r"```json?\s*", "", text).replace("```", "").strip()
    candidates = [text]
    if text.startswith("{{"):
        candidates.append(text[1:-1])
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match and match.group(0) not in candidates:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise json.JSONDecodeError("No JSON object found in LLM response", text, 0)


class BaseSentimentAnalyzer(ABC):
    """Interface for sentiment analyzers. Swap implementations freely."""

    @abstractmethod
    def analyze(self, event: NewsEvent, positions: dict | None = None) -> SentimentEvent:
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

    def analyze(self, event: NewsEvent, positions: dict | None = None) -> SentimentEvent:
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

# Cap output so a rambling LLM can't turn a 50-token JSON into 4000 tokens (42s calls).
# JSON-only replies fit comfortably; prose gets truncated and parsed conservatively.
_LLM_MAX_TOKENS = 500

_LLM_RETURN_JSON = """\
{{
  "symbols": ["{symbol}"],
  "sector": "technology",
  "sentiment": 0.5,
  "confidence": 0.8,
  "urgency": "normal"
}}"""


def _return_example(markets: str) -> str:
    """Return example using a symbol from a tradable market."""
    market_list = [m.strip().upper() for m in markets.split(",") if m.strip()]
    symbol = "0700.HK" if "HK" in market_list else "AAPL"
    return "\nReturn:\n" + _LLM_RETURN_JSON.format(symbol=symbol)

_MARKET_FORMATS = {
    "HK": (
        "- HK stocks: exactly 4 digits + .HK → 0700.HK (Tencent), 9988.HK (Alibaba), 0005.HK (HSBC), 0388.HK (HKEX), 0981.HK (SMIC), 0883.HK (CNOOC)\n"
        "  - WRONG examples — these will fail: 00700.HK ✗, 00005.HK ✗, 00002.HK ✗, 883.HK ✗, 981.HK ✗\n"
        "  - The ticker must match what Yahoo Finance recognizes. 5-digit HK codes (00700, 00005) do NOT exist on Yahoo Finance.\n"
        "- Try to find indirect links to HK stocks when the news is global (Fed decisions, oil, trade/tariffs, big-tech earnings, chip restrictions). "
        "Examples: US-China trade tension → Tencent (0700.HK), Alibaba (9988.HK), SMIC (0981.HK); oil news → CNOOC (0883.HK); rate news → HSBC (0005.HK).\n"
        "- Use confidence 0.3-0.6 for indirect links, 0.7-1.0 only for direct mentions.\n"
        "- Only return empty symbols if there is truly no meaningful connection to any HK stock."
    ),
    "US": (
        "- US stocks: plain uppercase ticker without suffix or exchange code → AAPL, TSLA, NVDA, MSFT.\n"
        "- Return well-known, actively traded US-listed stocks with valid Yahoo Finance tickers.\n"
        "- Prefer tickers directly affected by the news. Use confidence 0.7-1.0 for direct mentions, 0.3-0.6 for indirect links.\n"
        "- Only return empty symbols if the news has no meaningful connection to any US stock."
    ),
}


def _market_rules(markets: str) -> str:
    """Build market-specific rules for the LLM prompt."""
    market_list = [m.strip().upper() for m in markets.split(",") if m.strip()]
    lines = [f"- We can ONLY trade stocks on these markets: {', '.join(market_list) or 'NONE'}"]
    if not market_list:
        lines.append("- Return empty symbols — we cannot trade anything.")
        return "\n".join(lines)
    for m in market_list:
        guidance = _MARKET_FORMATS.get(m)
        if guidance:
            lines.append(guidance)
        else:
            lines.append(f"- Market '{m}' is unsupported — never return symbols for it.")
    return "\n".join(lines)


def _build_llm_prompt(headline: str, markets: str, positions: dict | None = None) -> str:
    parts = ["Analyze this financial news headline" +
             (" considering the current portfolio" if positions else "") +
             ". Return JSON only, no explanation.",
             f'\nHeadline: "{headline}"']
    if positions:
        pos_str = "\n".join(f"- {sym}" for sym in positions.keys()) or "None"
        parts.append(f"\nCurrent holdings:\n{pos_str}")
    parts.append("\nRules:")
    parts.append("- We trade CASH ONLY — no margin, no short selling, no borrowing.")
    parts.append(_market_rules(markets))
    if positions:
        parts.append("- Only list a holding for SELLING if the headline directly and specifically concerns that company or its sector/industry.")
        parts.append("- If the news does not directly concern a holding, leave it out of symbols entirely — even if the news is broadly negative.")
        parts.append("- Never return the full holdings list just because sentiment is negative.")
        parts.append("- Higher confidence if the news directly impacts our holdings.")
    parts.append("- Sentiment is from the perspective of the returned symbols (positive = those symbols go up).")
    parts.append(_return_example(markets))
    return "\n".join(parts)


class LLMSentimentAnalyzer(BaseSentimentAnalyzer):
    """LLM-based scorer. More accurate, needs API key.

    Supports any OpenAI-compatible API (OpenAI, Azure, opencode Zen, Ollama, local LLMs).
    Set OPENCODE_API_KEY to use opencode Zen (free big-pickle model by default).
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key: str | None = None
        self.base_url: str | None = None
        self.model: str | None = None
        opencode_key = api_key or os.getenv("OPENCODE_API_KEY")
        if opencode_key:
            self.api_key = opencode_key
            self.base_url = base_url or os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1")
            self.model = model or os.getenv("OPENCODE_MODEL", "big-pickle")
            logger.info("LLM provider: OpenCode (model=%s)", self.model)
        else:
            self.api_key = api_key or os.getenv("OPENAI_API_KEY")
            self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            logger.info("LLM provider: OpenAI (model=%s)", self.model)

    def _get_client(self):
        from openai import OpenAI
        return OpenAI(base_url=self.base_url, api_key=self.api_key)

    def analyze(self, event: NewsEvent, positions: dict | None = None) -> SentimentEvent:
        from src.settings import settings

        prompt = _build_llm_prompt(event.headline, settings.tradable_markets, positions)
        logger.info("Prompt built: %d chars, headline: %s", len(prompt), event.headline[:60])
        t0 = time.perf_counter()
        try:
            content = self._call_llm(prompt)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            data = _parse_llm_json(content)
        except json.JSONDecodeError as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.warning("LLM returned non-JSON after %.0fms (%s) — emitting neutral sentiment. Content: %.300r",
                           elapsed_ms, e, content)
            data = {}
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.error("LLM analysis failed after %.0fms: %s", elapsed_ms, e, exc_info=True)
            raise

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

    @retry(max_attempts=3, base_delay=1.0, exceptions=(Exception,))
    def _call_llm(self, prompt: str) -> str:
        client = self._get_client()
        t0 = time.perf_counter()
        logger.info("LLM call starting (model=%s, base_url=%s)", self.model, self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=_LLM_MAX_TOKENS,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000
        usage = resp.usage
        if usage:
            logger.info("LLM call done in %.0fms — prompt_tokens=%d completion_tokens=%d total=%d",
                        elapsed_ms, usage.prompt_tokens, usage.completion_tokens, usage.total_tokens)
        else:
            logger.info("LLM call done in %.0fms — usage unavailable", elapsed_ms)
        content = resp.choices[0].message.content
        return str(content) if content is not None else ""
