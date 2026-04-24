"""Reddit news source — scrapes subreddit posts via public JSON API.

No API key needed. Uses Reddit's public .json endpoints.
Rate limit: ~10 req/min without auth.
"""
import requests
from src.common.events import NewsEvent
from .newsapi_source import NewsSource


class RedditSource(NewsSource):
    """Fetch posts from finance subreddits. No API key required."""

    def __init__(self, subreddits: list[str] = None, limit: int = 20):
        super().__init__()
        self.subreddits = subreddits or ["wallstreetbets", "stocks", "investing"]
        self.limit = limit

    def fetch_latest(self) -> list[NewsEvent]:
        events = []
        for sub in self.subreddits:
            try:
                resp = requests.get(
                    f"https://www.reddit.com/r/{sub}/new.json?limit={self.limit}",
                    headers={"User-Agent": "EonTrading/1.0"},
                    timeout=10,
                )
                for post in resp.json().get("data", {}).get("children", []):
                    d = post["data"]
                    pid = d.get("id", "")
                    if self._check_seen(pid):
                        continue
                    events.append(NewsEvent(
                        source=f"reddit/{sub}",
                        headline=d.get("title", ""),
                        timestamp=self._epoch_to_iso(d.get("created_utc", 0)),
                        url=f"https://reddit.com{d.get('permalink', '')}",
                        body=d.get("selftext", "")[:500],
                    ))
            except Exception as e:
                print(f"Reddit error (r/{sub}): {e}")
        return events

    @staticmethod
    def _epoch_to_iso(epoch: float) -> str:
        from datetime import datetime
        return datetime.utcfromtimestamp(epoch).isoformat() + "Z"
