"""NewsWatcher: polls news sources, publishes raw news to event bus."""
import asyncio
import logging
from datetime import datetime

from src.common.clock import utcnow
from src.common.log_handler import ComponentFilter
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_NEWS
from src.common.news_poller import NewsPoller
from src.common.news_store import BaseNewsStore, MongoNewsStore, news_to_doc

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("newswatcher"))


class NewsWatcher:
    """Polls news sources and publishes raw news events.

    Optionally persists articles to MongoDB for later backtest/replay.
    Set persist_news=True or PERSIST_NEWS=1 env var to enable.
    """

    def __init__(self, bus: EventBus, sources: list = None, interval_sec: int = 120,
                 persist_seen: bool = True, persist_news: bool = False, publish: bool = True,
                 news_store: BaseNewsStore | None = None, db=None):
        self.bus = bus
        if persist_news and news_store is None and db is not None:
            news_store = MongoNewsStore(db)
        self._store = news_store
        self.poller = NewsPoller(sources=sources or [], interval_sec=interval_sec,
                                 persist_seen=persist_seen, news_store=news_store)
        self.last_poll: datetime | None = None
        self.last_poll_count: int = 0
        self._publish = publish
        if self._store is not None:
            try:
                self._store.ensure_news_indexes()
                logger.info("News persistence enabled")
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
                if self._store is not None:
                    try:
                        self._store.insert_news(news_to_doc(news, origin="live"))
                    except Exception as e:
                        logger.debug("News insert skipped: %s", e)
            if not events:
                logger.info("No new articles at %s", self.last_poll.strftime('%H:%M:%S'))
            else:
                logger.info("Fetched %d articles at %s", len(events), self.last_poll.strftime('%H:%M:%S'))
            await asyncio.sleep(self.poller.interval)

    async def _poll_concurrent(self):
        """Poll all sources concurrently, then dedup."""
        async def _fetch(source, timeout=30):
            return await asyncio.wait_for(
                source.fetch_latest(), timeout=timeout,
            )

        tasks = {asyncio.create_task(_fetch(s)): s for s in self.poller.sources}
        done, pending = await asyncio.wait(tasks, timeout=30)

        for task in pending:
            task.cancel()

        if not done:
            logger.warning("Poll cycle timed out after 30s")
            return []

        events = []
        for task in done:
            source = tasks[task]
            try:
                result = task.result()
            except asyncio.TimeoutError:
                logger.warning("Source %s timed out after 30s", source.__class__.__name__)
                continue
            except Exception as e:
                logger.error("Source %s failed: %s", source.__class__.__name__, e)
                continue
            events.extend(self.poller.filter_unseen(result))
            count = len(result)
            if count:
                logger.info("  %s: %d articles", source.__class__.__name__, count)
        return events
