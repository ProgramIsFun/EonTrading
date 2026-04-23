"""Shared news polling logic — used by both live trader and collector."""
from src.data.news.newsapi_source import NewsSource
from src.common.events import NewsEvent


class NewsPoller:
    """Polls news sources and deduplicates. Callbacks handle what to do with each article."""

    def __init__(self, sources: list[NewsSource] = None, interval_sec: int = 120):
        self.sources = sources or []
        self.interval = interval_sec

    def poll_once(self) -> list[NewsEvent]:
        """Fetch new articles from all sources. Dedup handled by each source's _seen set."""
        events = []
        for source in self.sources:
            events.extend(source.fetch_latest())
        return events
