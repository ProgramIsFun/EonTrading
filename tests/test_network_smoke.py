"""Smoke test: real HTTP calls to verify NewsWatcher actually fetches news.

Run with: pytest -m network
"""
import pytest

pytestmark = pytest.mark.network

from src.common.event_bus import LocalEventBus
from src.data.news.rss_source import RSSSource
from src.live.news_watcher import NewsWatcher


@pytest.mark.asyncio
async def test_rss_source_returns_real_news():
    bus = LocalEventBus()
    await bus.start()
    source = RSSSource()
    watcher = NewsWatcher(bus, sources=[source], persist_seen=False)

    events = await watcher._poll_concurrent()

    assert len(events) > 0
    assert all(e.headline for e in events)
    assert all(e.url for e in events)
    assert all(e.source == "rss" for e in events)
