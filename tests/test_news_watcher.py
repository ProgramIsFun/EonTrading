"""Tests for NewsWatcher concurrent polling and timeout."""
import asyncio
import time
from unittest.mock import patch

import pytest

from src.common.event_bus import LocalEventBus
from src.common.events import CHANNEL_NEWS, NewsEvent
from src.data.news.newsapi_source import NewsSource
from src.live.news_watcher import NewsWatcher


class FastSource(NewsSource):
    async def fetch_latest(self):
        return [NewsEvent(source="fast", headline="Fast news", timestamp="2026-01-01T00:00:00Z", url="http://fast/1", body="")]


class SlowSource(NewsSource):
    def __init__(self, delay: float = 2.0):
        super().__init__()
        self.delay = delay

    async def fetch_latest(self):
        await asyncio.sleep(self.delay)
        return [NewsEvent(source="slow", headline="Slow news", timestamp="2026-01-01T00:00:00Z", url="http://slow/1", body="")]


class FailingSource(NewsSource):
    async def fetch_latest(self):
        raise ConnectionError("source down")


@pytest.mark.asyncio
async def test_concurrent_polling_faster_than_sequential():
    """Multiple slow sources should complete in ~1x delay, not Nx."""
    bus = LocalEventBus()
    await bus.start()
    sources = [SlowSource(delay=0.3), SlowSource(delay=0.3), SlowSource(delay=0.3)]
    watcher = NewsWatcher(bus, sources=sources, persist_seen=False)

    start = time.monotonic()
    events = await watcher._poll_concurrent()
    elapsed = time.monotonic() - start

    assert len(events) == 3
    # Concurrent: ~0.3s. Sequential would be ~0.9s.
    assert elapsed < 0.7, f"Took {elapsed:.2f}s — sources not running concurrently"


@pytest.mark.asyncio
async def test_failing_source_doesnt_block_others():
    """One failing source shouldn't prevent others from returning results."""
    bus = LocalEventBus()
    await bus.start()
    sources = [FastSource(), FailingSource(), FastSource()]
    watcher = NewsWatcher(bus, sources=sources, persist_seen=False)

    events = await watcher._poll_concurrent()
    assert len(events) == 2
    assert all(e.source == "fast" for e in events)


@pytest.mark.asyncio
async def test_poll_timeout():
    """Sources exceeding the timeout should not block the cycle."""
    bus = LocalEventBus()
    await bus.start()
    sources = [SlowSource(delay=60)]  # way over timeout
    watcher = NewsWatcher(bus, sources=sources, persist_seen=False)

    from unittest.mock import patch
    # _poll_concurrent uses asyncio.wait_for(timeout=30). Patch it to raise
    # immediately so we don't actually wait 30s for the slow source.
    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        start = time.monotonic()
        events = await watcher._poll_concurrent()
        elapsed = time.monotonic() - start

    assert events == []
    assert elapsed < 1, f"Timeout didn't fire — took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_publishes_to_bus():
    """NewsWatcher should publish fetched events to the news channel."""
    bus = LocalEventBus()
    await bus.start()
    received = []
    await bus.subscribe(CHANNEL_NEWS, lambda msg: received.append(msg) or asyncio.sleep(0))

    sources = [FastSource()]
    watcher = NewsWatcher(bus, sources=sources, persist_seen=False)

    events = await watcher._poll_concurrent()
    for news in events:
        await bus.publish(CHANNEL_NEWS, news.to_dict())
    await asyncio.sleep(0.05)

    assert len(received) == 1
    assert received[0]["headline"] == "Fast news"


# ---------------------------------------------------------------------------
# Reddit source: only loaded when credentials exist
# ---------------------------------------------------------------------------

class TestRedditSourceAvailability:

    def test_not_available_without_credentials(self):
        from src.data.news.reddit_source import RedditSource
        with patch.dict("os.environ", {}, clear=True):
            source = RedditSource()
            assert source.available is False

    def test_available_with_credentials(self):
        from src.data.news.reddit_source import RedditSource
        with patch.dict("os.environ", {"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "secret"}):
            source = RedditSource()
            assert source.available is True

    def test_fetch_latest_returns_empty_when_no_credentials(self):
        from src.data.news.reddit_source import RedditSource
        with patch.dict("os.environ", {}, clear=True):
            source = RedditSource()
            events = asyncio.run(source.fetch_latest())
            assert events == []

    def test_loader_skips_reddit_without_credentials(self):
        from src.data.news.loader import build_news_sources
        with patch.dict("os.environ", {}, clear=True):
            sources, names = build_news_sources()
            assert "Reddit" not in names
            assert not any("reddit" in getattr(s, "_client_id", "") or
                          hasattr(s, "subreddits") for s in sources)

    def test_loader_includes_reddit_with_credentials(self):
        from src.data.news.loader import build_news_sources
        with patch.dict("os.environ", {"REDDIT_CLIENT_ID": "id", "REDDIT_CLIENT_SECRET": "secret"}):
            sources, names = build_news_sources()
            assert "Reddit" in names
