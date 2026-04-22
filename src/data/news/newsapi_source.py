"""News source interface and NewsAPI implementation."""
import os
import requests
from datetime import datetime, timedelta
from src.common.events import NewsEvent


class NewsSource:
    """Base class for news sources."""
    def fetch_latest(self) -> list[NewsEvent]:
        raise NotImplementedError


class NewsAPISource(NewsSource):
    """Fetch headlines from NewsAPI.org."""

    def __init__(self, api_key: str = None, categories: list[str] = None):
        self.api_key = api_key or os.getenv("NEWSAPI_KEY")
        self.base_url = "https://newsapi.org/v2"
        self.categories = categories or ["business"]
        self._seen = set()

    def fetch_latest(self, query: str = "stock market OR trading OR tariff OR earnings") -> list[NewsEvent]:
        events = []
        try:
            resp = requests.get(f"{self.base_url}/everything", params={
                "apiKey": self.api_key,
                "q": query,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 20,
                "from": (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }, timeout=10)
            data = resp.json()
            for article in data.get("articles", []):
                url = article.get("url", "")
                if url in self._seen:
                    continue
                self._seen.add(url)
                events.append(NewsEvent(
                    source="newsapi",
                    headline=article.get("title", ""),
                    timestamp=article.get("publishedAt", ""),
                    url=url,
                    body=article.get("description", ""),
                ))
        except Exception as e:
            print(f"NewsAPI error: {e}")
        return events
