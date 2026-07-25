"""Shared news polling logic — used by both live trader and collector."""
import logging

from src.common.events import NewsEvent
from src.data.news.newsapi_source import NewsSource

logger = logging.getLogger(__name__)


class NewsPoller:
    """Polls news sources and deduplicates. Callbacks handle what to do with each article."""

    def __init__(self, sources: list[NewsSource] = None, interval_sec: int = 120, persist_seen: bool = False, db=None):
        self.sources = sources or []
        self.interval = interval_sec
        self._seen_col = None
        if persist_seen:
            try:
                if db is None:
                    from src.data.utils.db_helper import get_db
                    db = get_db()
                self._seen_col = db["seen_urls"]
                self._seen_col.create_index("url", unique=True)
            except Exception:
                logger.warning("Failed to init persistent dedup — falling back to in-memory only", exc_info=True)

    def _is_seen(self, url: str) -> bool:
        if self._seen_col is None or not url:
            return False
        return self._seen_col.find_one({"url": url}) is not None

    def _mark_seen(self, url: str):
        if self._seen_col is not None and url:
            try:
                self._seen_col.insert_one({"url": url})
            except Exception:
                pass  # duplicate key — already seen

    def filter_unseen(self, events: list[NewsEvent]) -> list[NewsEvent]:
        """Deduplicate events against seen URLs. Marks seen URLs as processed."""
        out = []
        for event in events:
            if self._seen_col is not None:
                if self._is_seen(event.url):
                    continue
                self._mark_seen(event.url)
            out.append(event)
        return out

    async def poll_once(self) -> list[NewsEvent]:
        """Fetch new articles from all sources. Dedup handled by each source's _seen set + optional MongoDB."""
        raw = []
        for source in self.sources:
            raw.extend(await source.fetch_latest())
        return self.filter_unseen(raw)
