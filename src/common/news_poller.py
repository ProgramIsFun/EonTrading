"""Shared news polling logic — used by both live trader and collector."""
import logging

logger = logging.getLogger(__name__)


class NewsPoller:
    """Polls news sources and deduplicates. Sources are now async."""

    def __init__(self, sources: list = None, interval_sec: int = 120, persist_seen: bool = False):
        self.sources = sources or []
        self.interval = interval_sec
        self._seen_col = None
        if persist_seen:
            try:
                from src.data.utils.db_helper import get_mongo_client
                self._seen_col = get_mongo_client()["EonTradingDB"]["seen_urls"]
            except Exception:
                logger.warning("Failed to init persistent dedup — falling back to in-memory only", exc_info=True)

    async def _init_index(self):
        if self._seen_col is not None:
            try:
                await self._seen_col.create_index("url", unique=True)
            except Exception:
                pass

    async def _is_seen(self, url: str) -> bool:
        if self._seen_col is None or not url:
            return False
        return (await self._seen_col.find_one({"url": url})) is not None

    async def _mark_seen(self, url: str):
        if self._seen_col is not None and url:
            try:
                await self._seen_col.insert_one({"url": url})
            except Exception:
                pass

    async def poll_once(self) -> list:
        events = []
        for source in self.sources:
            for event in await source.fetch_latest():
                if self._seen_col is not None:
                    if await self._is_seen(event.url):
                        continue
                    await self._mark_seen(event.url)
                events.append(event)
        return events
