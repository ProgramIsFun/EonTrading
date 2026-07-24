"""Reddit news source — fetches subreddit posts via OAuth2 API.

Requires REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET env vars.
Create an app at https://www.reddit.com/prefs/apps (choose "script").
"""
import logging
import os
from datetime import datetime, timezone

import httpx

from src.common.events import NewsEvent
from src.common.retry import retry

from .newsapi_source import NewsSource

logger = logging.getLogger(__name__)

_warned_missing = False


class RedditSource(NewsSource):
    """Fetch posts from finance subreddits via Reddit OAuth2."""

    def __init__(self, subreddits: list[str] = None, limit: int = 20):
        super().__init__()
        self.subreddits = subreddits or ["wallstreetbets", "stocks", "investing"]
        self.limit = limit
        self._client_id = os.getenv("REDDIT_CLIENT_ID", "")
        self._client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        self._token: str | None = None
        self._client = httpx.AsyncClient(timeout=10)

    @property
    def available(self) -> bool:
        return bool(self._client_id and self._client_secret)

    async def fetch_latest(self) -> list[NewsEvent]:
        global _warned_missing
        if not self.available:
            if not _warned_missing:
                logger.warning("Reddit skipped: set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to enable")
                _warned_missing = True
            return []

        if not self._token:
            await self._authenticate()

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

    async def _authenticate(self):
        resp = await self._client.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(self._client_id, self._client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": "EonTrading/1.0"},
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        self._client.headers["Authorization"] = f"Bearer {self._token}"
        self._client.headers["User-Agent"] = "EonTrading/1.0"

    @retry(max_attempts=3, base_delay=2.0, exceptions=(httpx.RequestError, httpx.HTTPStatusError))
    async def _fetch_sub(self, sub: str):
        resp = await self._client.get(
            f"https://oauth.reddit.com/r/{sub}/new?limit={self.limit}",
        )
        resp.raise_for_status()
        return resp

    @staticmethod
    def _epoch_to_iso(epoch: float) -> str:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
