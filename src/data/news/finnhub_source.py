"""Finnhub news source — real-time market news.

Free tier: 60 calls/min. Get key at https://finnhub.io/
"""
import os
import requests
from datetime import datetime, timedelta
from src.common.events import NewsEvent
from .newsapi_source import NewsSource


class FinnhubSource(NewsSource):
    """Fetch market news from Finnhub.io."""

    def __init__(self, api_key: str = None, category: str = "general"):
        self.api_key = api_key or os.getenv("FINNHUB_KEY")
        self.category = category  # general, forex, crypto, merger

    def fetch_latest(self) -> list[NewsEvent]:
        if not self.api_key:
            return []
        events = []
        try:
            resp = requests.get("https://finnhub.io/api/v1/news", params={
                "token": self.api_key,
                "category": self.category,
            }, timeout=10)
            for article in resp.json():
                uid = article.get("id", article.get("url", ""))
                if self._check_seen(uid):
                    continue
                events.append(NewsEvent(
                    source="finnhub",
                    headline=article.get("headline", ""),
                    timestamp=datetime.utcfromtimestamp(article.get("datetime", 0)).isoformat() + "Z",
                    url=article.get("url", ""),
                    body=article.get("summary", ""),
                ))
        except Exception as e:
            print(f"Finnhub error: {e}")
        return events
