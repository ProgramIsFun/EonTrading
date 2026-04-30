"""Shared news polling logic — used by both live trader and collector."""
import logging
from src.data.news.newsapi_source import NewsSource
from src.common.events import NewsEvent

logger = logging.getLogger(__name__)


class NewsPoller:
    """Polls news sources and deduplicates. Callbacks handle what to do with each article."""

    def __init__(self, sources: list[NewsSource] = None, interval_sec: int = 120, persist_seen: bool = False):
        self.sources = sources or []
        self.interval = interval_sec
        self._seen_col = None
        if persist_seen:
            try:
                from src.data.utils.db_helper import get_mongo_client
                self._seen_col = get_mongo_client()["EonTradingDB"]["seen_urls"]
                self._seen_col.create_index("url", unique=True)
            except Exception:
                logger.warning("Failed to init persistent dedup — falling back to in-memory only", exc_info=True)

    def _is_seen(self, url: str) -> bool:
        if not self._seen_col or not url:
            return False
        return self._seen_col.find_one({"url": url}) is not None

    def _mark_seen(self, url: str):
        if self._seen_col and url:
            try:
                self._seen_col.insert_one({"url": url})
            except Exception:
                pass  # duplicate key — already seen

    def poll_once(self) -> list[NewsEvent]:
        """Fetch new articles from all sources. Dedup handled by each source's _seen set + optional MongoDB."""
        events = []
        for source in self.sources:
            for event in source.fetch_latest():
                if self._seen_col:
                    if self._is_seen(event.url):
                        continue
                    self._mark_seen(event.url)
                events.append(event)
        return events
