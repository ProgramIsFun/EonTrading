"""News source interface and NewsAPI implementation."""
import logging
import os
from datetime import datetime, timedelta

import requests

from src.common.clock import utcnow
from src.common.events import NewsEvent
from src.common.retry import retry

logger = logging.getLogger(__name__)


class NewsSource:
    """Base class for news sources."""
    MAX_SEEN = 5000  # cap in-memory dedup set to prevent unbounded growth

    def __init__(self):
        self._seen: dict[str, int] = {}  # key → insertion order
        self._seen_counter = 0

    def _check_seen(self, key: str) -> bool:
        if not key:
            return False
        if key in self._seen:
            return True
        if len(self._seen) >= self.MAX_SEEN:
            # Evict oldest 20%
            cutoff = sorted(self._seen.values())[self.MAX_SEEN // 5]
            self._seen = {k: v for k, v in self._seen.items() if v > cutoff}
        self._seen_counter += 1
        self._seen[key] = self._seen_counter
        return False

    def fetch_latest(self) -> list[NewsEvent]:
        raise NotImplementedError


class NewsAPISource(NewsSource):
    """Fetch headlines from NewsAPI.org."""

    def __init__(self, api_key: str = None, categories: list[str] = None):
        super().__init__()
        self.api_key = api_key or os.getenv("NEWSAPI_KEY")
        self.base_url = "https://newsapi.org/v2"
        self.categories = categories or ["business"]

    def fetch_latest(self, query: str = "stock market OR trading OR tariff OR earnings") -> list[NewsEvent]:
        """Fetch from NewsAPI /v2/everything.

        Response: { "articles": [{ "title", "url", "publishedAt", "description", "source": {"name"} }] }
        """
        events = []
        try:
            resp = self._fetch_with_retry(query)
            data = resp.json()
            for article in data.get("articles", []):
                url = article.get("url", "")
                if self._check_seen(url):
                    continue
                events.append(NewsEvent(
                    source="newsapi",
                    headline=article.get("title", ""),
                    timestamp=article.get("publishedAt", ""),
                    url=url,
                    body=article.get("description", ""),
                ))
        except Exception as e:
            logger.error("NewsAPI error: %s", e)
        return events

    @retry(max_attempts=3, base_delay=2.0, exceptions=(requests.RequestException, requests.Timeout))
    def _fetch_with_retry(self, query: str):
        resp = requests.get(f"{self.base_url}/everything", params={
            "apiKey": self.api_key,
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 20,
            "from": (utcnow() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, timeout=10)
        resp.raise_for_status()
        return resp
