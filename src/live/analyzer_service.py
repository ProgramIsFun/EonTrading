"""AnalyzerService: subscribes to [news], queries positions, scores sentiment, publishes to [sentiment]."""
import logging
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_NEWS, CHANNEL_SENTIMENT, NewsEvent
from src.strategies.sentiment import BaseSentimentAnalyzer, KeywordSentimentAnalyzer

logger = logging.getLogger(__name__)


class AnalyzerService:
    """Listens to raw news, analyzes with portfolio context, publishes sentiment."""

    def __init__(self, bus: EventBus, analyzer: BaseSentimentAnalyzer = None, get_positions=None):
        self.bus = bus
        self.analyzer = analyzer or KeywordSentimentAnalyzer()
        self.get_positions = get_positions  # callable → {symbol: shares}

    async def start(self):
        await self.bus.subscribe(CHANNEL_NEWS, self._on_news)

    async def _on_news(self, msg: dict):
        event = NewsEvent.from_dict(msg)
        positions = self.get_positions() if self.get_positions else None
        sentiment = self.analyzer.analyze(event, positions=positions)
        if sentiment.confidence > 0:
            await self.bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
            logger.info("[%+.2f] %s", sentiment.sentiment, sentiment.headline[:80])
