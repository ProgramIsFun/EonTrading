"""NewsWatcher: polls news sources, publishes raw news to event bus."""
import asyncio
import logging
from datetime import datetime
from src.common.clock import utcnow
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_NEWS
from src.common.news_poller import NewsPoller

logger = logging.getLogger(__name__)


class NewsWatcher:
    """Polls news sources and publishes raw news events. That's it."""

    def __init__(self, bus: EventBus, sources: list = None, interval_sec: int = 120, persist_seen: bool = True):
        self.bus = bus
        self.poller = NewsPoller(sources=sources or [], interval_sec=interval_sec, persist_seen=persist_seen)
        self.last_poll: datetime | None = None
        self.last_poll_count: int = 0

    async def run(self):
        logger.info("NewsWatcher started, polling every %ds", self.poller.interval)
        while True:
            events = self.poller.poll_once()
            self.last_poll = utcnow()
            self.last_poll_count = len(events)
            for news in events:
                await self.bus.publish(CHANNEL_NEWS, news.to_dict())
            if not events:
                logger.info("No new articles at %s", self.last_poll.strftime('%H:%M:%S'))
            await asyncio.sleep(self.poller.interval)
