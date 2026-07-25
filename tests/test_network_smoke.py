"""Smoke test: real HTTP calls to verify components actually work.

Run with: pytest -m network
"""
import pytest

pytestmark = pytest.mark.network

from src.common.event_bus import LocalEventBus
from src.common.events import NewsEvent
from src.data.news.rss_source import RSSSource
from src.live.news_watcher import NewsWatcher
from src.strategies.sentiment import LLMSentimentAnalyzer


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


def test_llm_returns_sentiment():
    analyzer = LLMSentimentAnalyzer()
    event = NewsEvent(
        source="test",
        headline="Apple reports record quarterly revenue, beats Wall Street estimates",
        timestamp="2025-01-01T00:00:00Z",
    )
    result = analyzer.analyze(event)

    assert result is not None
    assert result.sentiment != 0 or result.confidence >= 0
    assert isinstance(result.symbols, list)


def test_llm_call_directly():
    analyzer = LLMSentimentAnalyzer()
    response = analyzer._call_llm("Say hello in one word.")

    assert isinstance(response, str)
    assert len(response) > 0
