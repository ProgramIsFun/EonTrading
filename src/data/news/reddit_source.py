"""Reddit news source — scrapes subreddit posts via public JSON API."""
import logging
from datetime import datetime, timezone

import httpx

from src.common.events import NewsEvent
from src.common.retry import retry

from .newsapi_source import NewsSource

logger = logging.getLogger(__name__)


class RedditSource(NewsSource):
    """Fetch posts from finance subreddits. No API key required."""

    def __init__(self, subreddits: list[str] = None, limit: int = 20):
        super().__init__()
        self.subreddits = subreddits or ["wallstreetbets", "stocks", "investing"]
        self.limit = limit

    async def fetch_latest(self) -> list[NewsEvent]:
        events = []
        for sub in self.subreddits:
            try:
                resp = await self._fetch_sub(sub)
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
                logger.error("Reddit error (r/%s): %s", sub, e)
        return events

    @retry(max_attempts=3, base_delay=2.0, exceptions=(httpx.RequestError,))
    async def _fetch_sub(self, sub: str):
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://www.reddit.com/r/{sub}/new.json?limit={self.limit}",
                headers={"User-Agent": "EonTrading/1.0"},
            )
            resp.raise_for_status()
            return resp

    @staticmethod
    def _epoch_to_iso(epoch: float) -> str:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
