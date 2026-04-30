"""Sentiment analysis interface and implementations."""
import re
import json
import os
import logging
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

LLM_PROMPT = """Analyze this financial news headline. Return JSON only, no explanation.

Headline: "{headline}"

Rules:
- We trade CASH ONLY — no margin, no leverage, no short selling, no borrowing. Maximum loss is capped at initial capital.
- Because we cannot short, use inverse ETFs to profit from market drops: SQQQ (inverse Nasdaq), SH (inverse S&P 500), SDOW (inverse Dow). These are regular stocks we buy with cash.
- If the news is bearish for the broad market (e.g. tariffs, recession, war), return inverse ETFs with POSITIVE sentiment (they go up when market drops).
- For individual stock news, return the affected tickers.
- Sentiment is from the perspective of the returned symbols (positive = those symbols go up).

Return:
{{
  "symbols": ["AAPL"],       // affected stock tickers or inverse ETFs
  "sector": "technology",    // affected sector or empty
  "sentiment": 0.5,          // -1.0 (very bearish) to +1.0 (very bullish) for the returned symbols
  "confidence": 0.8,         // 0.0 to 1.0
  "urgency": "normal"        // "low", "normal", "high"
}}"""

LLM_PROMPT_WITH_POSITIONS = """Analyze this financial news headline considering the current portfolio. Return JSON only, no explanation.

Headline: "{headline}"

Current holdings:
{positions}

Rules:
- We trade CASH ONLY — no margin, no leverage, no short selling, no borrowing. Maximum loss is capped at initial capital.
- Because we cannot short, use inverse ETFs to profit from market drops: SQQQ (inverse Nasdaq), SH (inverse S&P 500), SDOW (inverse Dow). These are regular stocks we buy with cash.
- If the news is bearish for the broad market, return inverse ETFs with POSITIVE sentiment + return held stocks with NEGATIVE sentiment (so we sell them).
- Sentiment is from the perspective of the returned symbols (positive = those symbols go up).
- Higher confidence if the news directly impacts our holdings.

Return:
{{
  "symbols": ["AAPL"],       // ALL affected tickers + inverse ETFs if applicable
  "sector": "technology",    // affected sector or empty
  "sentiment": 0.5,          // -1.0 to +1.0 for the returned symbols
  "confidence": 0.8,         // 0.0 to 1.0, higher if it affects our holdings
  "urgency": "normal"        // "low", "normal", "high"
}}"""


class LLMSentimentAnalyzer(BaseSentimentAnalyzer):
    """LLM-based scorer. More accurate, needs API key.

    Supports any OpenAI-compatible API (OpenAI, Ollama, local LLMs).
    """

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.api_version = os.getenv("OPENAI_API_VERSION", "")
        self._is_azure = "azure" in self.base_url

    def analyze(self, event: NewsEvent, positions: dict = None) -> SentimentEvent:
        import requests

        if positions:
            pos_str = "\n".join(f"- {sym}" for sym in positions.keys()) or "None"
            prompt = LLM_PROMPT_WITH_POSITIONS.format(headline=event.headline, positions=pos_str)
        else:
            prompt = LLM_PROMPT.format(headline=event.headline)
        try:
            content = self._call_llm(prompt)
            # Extract JSON from response (handle markdown code blocks)
            content = re.sub(r"```json?\s*", "", content).replace("```", "").strip()
            data = json.loads(content)

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
            logger.error("LLM analysis failed: %s", e)
            return SentimentEvent(
                source=event.source, headline=event.headline,
                timestamp=event.timestamp,
                analyzed_at=utcnow().isoformat() + "Z",
            )

    @retry(max_attempts=3, base_delay=1.0, exceptions=(Exception,))
    def _call_llm(self, prompt: str) -> str:
        import requests
        url = f"{self.base_url}/chat/completions"
        headers = {"api-key": self.api_key} if self._is_azure else {"Authorization": f"Bearer {self.api_key}"}
        params = {"api-version": self.api_version} if self._is_azure and self.api_version else {}
        resp = requests.post(
            url, headers=headers, params=params,
            json={"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
