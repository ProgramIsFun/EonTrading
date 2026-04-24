"""RSS feed news source — works with any RSS/Atom feed, no API key needed.

Good free feeds:
  - https://feeds.finance.yahoo.com/rss/2.0/headline?s=AAPL&region=US&lang=en-US
  - https://www.cnbc.com/id/100003114/device/rss/rss.html  (CNBC top news)
  - https://feeds.reuters.com/reuters/businessNews  (Reuters business)
"""
import os
import requests
import re
from datetime import datetime
from src.common.events import NewsEvent
from .newsapi_source import NewsSource


class RSSSource(NewsSource):
    """Fetch news from RSS/Atom feeds. No API key required."""

    def __init__(self, feeds: list[str] = None):
        self.feeds = feeds or [
            "https://feeds.finance.yahoo.com/rss/2.0/headline?region=US&lang=en-US",
            "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        ]

    def fetch_latest(self) -> list[NewsEvent]:
        events = []
        for feed_url in self.feeds:
            try:
                resp = requests.get(feed_url, timeout=10, headers={"User-Agent": "EonTrading/1.0"})
                events.extend(self._parse_feed(resp.text, feed_url))
            except Exception as e:
                print(f"RSS error ({feed_url[:50]}): {e}")
        return events

    def _parse_feed(self, xml: str, feed_url: str) -> list[NewsEvent]:
        """Simple regex XML parser — no lxml/feedparser dependency."""
        events = []
        items = re.findall(r"<item>(.*?)</item>", xml, re.DOTALL)
        if not items:  # try Atom format
            items = re.findall(r"<entry>(.*?)</entry>", xml, re.DOTALL)
        for item in items:
            title = self._tag(item, "title")
            link = self._tag(item, "link") or self._attr(item, "link", "href")
            pub = self._tag(item, "pubDate") or self._tag(item, "published") or self._tag(item, "updated")
            desc = self._tag(item, "description") or self._tag(item, "summary") or ""

            if not title or self._check_seen(link):
                continue

            # Strip HTML tags from description
            desc = re.sub(r"<[^>]+>", "", desc).strip()

            events.append(NewsEvent(
                source="rss",
                headline=title,
                timestamp=pub or datetime.utcnow().isoformat() + "Z",
                url=link or "",
                body=desc[:500],
            ))
        return events

    @staticmethod
    def _tag(xml: str, tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, re.DOTALL)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _attr(xml: str, tag: str, attr: str) -> str:
        m = re.search(rf'<{tag}[^>]*{attr}="([^"]*)"', xml)
        return m.group(1) if m else ""
