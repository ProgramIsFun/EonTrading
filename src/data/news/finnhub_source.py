"""Finnhub news source — real-time market news.

Free tier: 60 calls/min. Get key at https://finnhub.io/
"""
import logging
import os
from datetime import datetime, timezone

import requests

from src.common.events import NewsEvent
from src.common.retry import retry

from .newsapi_source import NewsSource

logger = logging.getLogger(__name__)


class FinnhubSource(NewsSource):
    """Fetch market news from Finnhub.io."""

    def __init__(self, api_key: str = None, category: str = "general"):
        super().__init__()
        self.api_key = api_key or os.getenv("FINNHUB_KEY")
        self.category = category  # general, forex, crypto, merger

    def fetch_latest(self) -> list[NewsEvent]:
        """Fetch from Finnhub /api/v1/news.

        Response: [{ "id", "headline", "url", "summary", "datetime" (epoch), "source", "category" }]
        """
        if not self.api_key:
            return []
        events = []
        try:
            resp = self._fetch_with_retry()
            for article in resp.json():
                uid = article.get("id", article.get("url", ""))
                if self._check_seen(uid):
                    continue
                events.append(NewsEvent(
                    source="finnhub",
                    headline=article.get("headline", ""),
                    timestamp=datetime.fromtimestamp(article.get("datetime", 0), tz=timezone.utc).isoformat(),
                    url=article.get("url", ""),
                    body=article.get("summary", ""),
                ))
        except Exception as e:
            logger.error("Finnhub error: %s", e)
        return events

    @retry(max_attempts=3, base_delay=2.0, exceptions=(requests.RequestException, requests.Timeout))
    def _fetch_with_retry(self):
        resp = requests.get("https://finnhub.io/api/v1/news", params={
            "token": self.api_key,
            "category": self.category,
        }, timeout=10)
        resp.raise_for_status()
        return resp
