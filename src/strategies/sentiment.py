"""Sentiment analysis for news headlines."""
import re
from datetime import datetime
from ..common.events import NewsEvent, SentimentEvent

# S&P 500 major tickers and their common names
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

# Simple keyword-based sentiment (fast, no dependencies)
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


class SentimentAnalyzer:
    """Keyword-based sentiment scorer. Fast, no ML dependencies."""

    def analyze(self, event: NewsEvent) -> SentimentEvent:
        text = (event.headline + " " + event.body).lower()

        # Extract symbols
        symbols = []
        for keyword, ticker in TICKER_MAP.items():
            if keyword in text and ticker not in symbols:
                symbols.append(ticker)

        # Detect sector
        sector = ""
        for sec, keywords in SECTOR_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                sector = sec
                break

        # Score sentiment
        bull = sum(1 for w in BULLISH_WORDS if w in text)
        bear = sum(1 for w in BEARISH_WORDS if w in text)
        total = bull + bear
        if total == 0:
            sentiment = 0.0
            confidence = 0.0
        else:
            sentiment = (bull - bear) / total  # -1 to +1
            confidence = min(total / 5, 1.0)   # more keywords = more confident

        # Urgency based on strong words
        urgency = "normal"
        if any(w in text for w in ["crash", "surge", "ban", "war", "tariff"]):
            urgency = "high"

        return SentimentEvent(
            source=event.source,
            headline=event.headline,
            timestamp=event.timestamp,
            analyzed_at=datetime.utcnow().isoformat() + "Z",
            symbols=symbols,
            sector=sector,
            sentiment=round(sentiment, 3),
            confidence=round(confidence, 3),
            urgency=urgency,
        )
