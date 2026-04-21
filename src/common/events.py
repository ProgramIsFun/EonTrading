"""Event message schemas for the EventBus."""
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class NewsEvent:
    """Published by news watchers, consumed by sentiment analyzer."""
    source: str                    # "newsapi", "truthsocial", "reddit", "finnhub"
    headline: str
    timestamp: str                 # ISO format UTC
    url: str = ""
    body: str = ""                 # full text if available

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "NewsEvent":
        return NewsEvent(**{k: v for k, v in d.items() if k in NewsEvent.__dataclass_fields__})


@dataclass
class SentimentEvent:
    """Published by sentiment analyzer, consumed by traders."""
    source: str                    # original news source
    headline: str
    timestamp: str                 # when the news happened
    analyzed_at: str               # when we scored it
    symbols: list[str] = field(default_factory=list)   # affected tickers
    sector: str = ""               # "technology", "energy", etc.
    sentiment: float = 0.0         # -1.0 (very bearish) to +1.0 (very bullish)
    confidence: float = 0.0        # 0.0 to 1.0, how sure the model is
    urgency: str = "normal"        # "low", "normal", "high"

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "SentimentEvent":
        return SentimentEvent(**{k: v for k, v in d.items() if k in SentimentEvent.__dataclass_fields__})


@dataclass
class TradeEvent:
    """Published by traders, consumed by execution engine or logger."""
    symbol: str
    action: str                    # "buy", "sell"
    reason: str                    # "sentiment:-0.8 on tariff news"
    timestamp: str
    price: float = 0.0             # target or market price
    size: float = 1.0              # fraction of capital

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "TradeEvent":
        return TradeEvent(**{k: v for k, v in d.items() if k in TradeEvent.__dataclass_fields__})


# Channel names
CHANNEL_NEWS = "news"              # NewsEvent
CHANNEL_SENTIMENT = "sentiment"    # SentimentEvent
CHANNEL_TRADE = "trade"            # TradeEvent
