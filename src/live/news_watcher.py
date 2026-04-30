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
            events = await self._poll_concurrent()
            self.last_poll = utcnow()
            self.last_poll_count = len(events)
            for news in events:
                await self.bus.publish(CHANNEL_NEWS, news.to_dict())
            if not events:
                logger.info("No new articles at %s", self.last_poll.strftime('%H:%M:%S'))
            await asyncio.sleep(self.poller.interval)

    async def _poll_concurrent(self):
        """Poll all sources concurrently, then dedup."""
        try:
            results = await asyncio.wait_for(asyncio.gather(*[
                asyncio.to_thread(source.fetch_latest) for source in self.poller.sources
            ], return_exceptions=True), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("Poll cycle timed out after 30s")
            return []
        events = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("Source %s failed: %s", self.poller.sources[i].__class__.__name__, result)
                continue
            for event in result:
                if self.poller._seen_col:
                    if self.poller._is_seen(event.url):
                        continue
                    self.poller._mark_seen(event.url)
                events.append(event)
        return events
