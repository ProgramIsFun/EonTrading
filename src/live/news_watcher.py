"""NewsWatcher: polls news sources, publishes raw news to event bus."""
import asyncio
import logging
from datetime import datetime

from src.common.clock import utcnow
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_NEWS
from src.common.news_poller import NewsPoller
from src.common.news_store import news_to_doc

logger = logging.getLogger(__name__)


class NewsWatcher:
    """Polls news sources and publishes raw news events.

    Optionally persists articles to MongoDB for later backtest/replay.
    Set persist_news=True or PERSIST_NEWS=1 env var to enable.
    """

    def __init__(self, bus: EventBus, sources: list = None, interval_sec: int = 120,
                 persist_seen: bool = True, persist_news: bool = False, publish: bool = True):
        self.bus = bus
        self.poller = NewsPoller(sources=sources or [], interval_sec=interval_sec, persist_seen=persist_seen)
        self.last_poll: datetime | None = None
        self.last_poll_count: int = 0
        self._publish = publish
        self._news_col = None
        if persist_news:
            try:
                from src.data.utils.db_helper import get_mongo_client
                self._news_col = get_mongo_client()["EonTradingDB"]["news"]
                self._news_col.create_index("url", unique=True, sparse=True)
                logger.info("News persistence enabled — writing to MongoDB EonTradingDB.news")
            except Exception:
                logger.warning("Failed to init news persistence", exc_info=True)

    async def run(self):
        logger.info("NewsWatcher started, polling every %ds", self.poller.interval)
        while True:
            try:
                events = await self._poll_concurrent()
            except Exception:
                logger.error("Poll failed", exc_info=True)
                events = []
            self.last_poll = utcnow()
            self.last_poll_count = len(events)
            for news in events:
                if self._publish:
                    await self.bus.publish(CHANNEL_NEWS, news.to_dict())
                if self._news_col is not None:
                    try:
                        self._news_col.insert_one(news_to_doc(news, origin="live"))
                    except Exception:
                        pass  # duplicate URL
            if not events:
                logger.info("No new articles at %s", self.last_poll.strftime('%H:%M:%S'))
            else:
                logger.info("Fetched %d articles at %s", len(events), self.last_poll.strftime('%H:%M:%S'))
            await asyncio.sleep(self.poller.interval)

    async def _poll_concurrent(self):
        """Poll all sources concurrently, then dedup.

        Uses to_thread because news sources use synchronous requests.get() —
        calling them directly would block the async event loop.
        """
        try:
            results = await asyncio.wait_for(asyncio.gather(*[
                asyncio.to_thread(source.fetch_latest) for source in self.poller.sources
            ], return_exceptions=True), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("Poll cycle timed out after 30s")
            return []
        events = []
        for i, result in enumerate(results):
            source_name = self.poller.sources[i].__class__.__name__
            if isinstance(result, Exception):
                logger.error("Source %s failed: %s", source_name, result)
                continue
            count = 0
            for event in result:
                if self.poller._seen_col is not None:
                    if self.poller._is_seen(event.url):
                        continue
                    self.poller._mark_seen(event.url)
                events.append(event)
                count += 1
            if count:
                logger.info("  %s: %d articles", source_name, count)
        return events
