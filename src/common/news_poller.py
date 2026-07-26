"""Shared news polling logic — used by both live trader and collector."""
import logging

from src.common.events import NewsEvent

logger = logging.getLogger(__name__)


class NewsPoller:
    """Polls news sources and deduplicates. Callbacks handle what to do with each article."""

    def __init__(self, sources: list = None, interval_sec: int = 120,
                 persist_seen: bool = False, news_store=None):
        self.sources = sources or []
        self.interval = interval_sec
        self._store = None
        if persist_seen and news_store is not None:
            try:
                news_store.ensure_seen_indexes()
                self._store = news_store
            except Exception:
                logger.warning("Failed to init persistent dedup — falling back to in-memory only", exc_info=True)

    def _is_seen(self, url: str) -> bool:
        if self._store is None or not url:
            return False
        return self._store.is_seen(url)

    def _mark_seen(self, url: str):
        if self._store is not None and url:
            try:
                self._store.mark_seen(url)
            except Exception:
                pass  # duplicate key — already seen

    def filter_unseen(self, events: list[NewsEvent]) -> list[NewsEvent]:
        """Deduplicate events against seen URLs. Marks seen URLs as processed."""
        out = []
        for event in events:
            if self._store is not None:
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
