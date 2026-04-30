"""AnalyzerService: subscribes to [news], queries positions, scores sentiment, publishes to [sentiment]."""
import asyncio
import logging
from datetime import datetime
from src.common.clock import utcnow
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_NEWS, CHANNEL_SENTIMENT, NewsEvent
from src.strategies.sentiment import BaseSentimentAnalyzer, KeywordSentimentAnalyzer

logger = logging.getLogger(__name__)

MAX_NEWS_AGE_SEC = 600  # skip news older than 10 minutes


class AnalyzerService:
    """Listens to raw news, analyzes with portfolio context, publishes sentiment."""

    def __init__(self, bus: EventBus, analyzer: BaseSentimentAnalyzer = None,
                 get_positions=None, max_age_sec: int = MAX_NEWS_AGE_SEC):
        self.bus = bus
        self.analyzer = analyzer or KeywordSentimentAnalyzer()
        self.get_positions = get_positions  # callable → {symbol: shares}
        self.max_age_sec = max_age_sec

    async def start(self):
        await self.bus.subscribe(CHANNEL_NEWS, self._on_news)

    def _is_stale(self, event: NewsEvent) -> bool:
        if not event.timestamp or self.max_age_sec <= 0:
            return False
        try:
            ts = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
            age = (utcnow().replace(tzinfo=None) - ts).total_seconds()
            if age > self.max_age_sec:
                logger.info("Skipping stale news (%.0fs old): %s", age, event.headline[:60])
                return True
        except (ValueError, TypeError):
            pass
        return False

    async def _on_news(self, msg: dict):
        event = NewsEvent.from_dict(msg)
        if self._is_stale(event):
            return
        # Run synchronous MongoDB + LLM calls off the event loop
        positions = await asyncio.to_thread(self.get_positions) if self.get_positions else None
        sentiment = await asyncio.to_thread(self.analyzer.analyze, event, positions)
        if sentiment.confidence > 0:
            await self.bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
            logger.info("[%+.2f] %s", sentiment.sentiment, sentiment.headline[:80])
