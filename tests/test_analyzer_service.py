"""Tests for AnalyzerService — stale news filtering, position-aware dispatch."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.common.events import NewsEvent, SentimentEvent
from src.live.analyzer_service import AnalyzerService


class FakeAnalyzer:
    """Simulates an analyzer with a mock .analyze method."""

    def __init__(self, **overrides):
        defaults = dict(source="test", headline="", timestamp="", analyzed_at="",
                        symbols=[], sentiment=0.0, confidence=0.0)
        defaults.update(overrides)
        self._result = SentimentEvent(**defaults)
        self.analyze = MagicMock(return_value=self._result)


DISABLE_STALE = {"max_age_sec": 0}


@pytest.fixture
def bus():
    return AsyncMock()


@pytest.fixture
def analyzer():
    return FakeAnalyzer()


@pytest.fixture
def svc(bus, analyzer):
    return AnalyzerService(bus, analyzer=analyzer, get_positions=lambda: {}, **DISABLE_STALE)


class TestIsStale:
    def test_no_timestamp_not_stale(self, svc):
        event = NewsEvent(source="t", headline="h", timestamp="", url="", body="")
        assert svc._is_stale(event) is False

    def test_max_age_zero_not_stale(self, svc):
        svc.max_age_sec = 0
        event = NewsEvent(source="t", headline="h", timestamp="2026-05-31T10:00:00Z", url="", body="")
        assert svc._is_stale(event) is False

    def test_recent_news_not_stale(self, svc):
        event = NewsEvent(source="t", headline="h", timestamp="2026-05-31T10:00:00Z", url="", body="")
        with patch("src.live.analyzer_service.utcnow") as mock_now:
            mock_now.return_value = __import__("datetime").datetime(2026, 5, 31, 10, 3, 0)
            assert svc._is_stale(event) is False

    def test_old_news_is_stale(self, svc):
        svc.max_age_sec = 60
        event = NewsEvent(source="t", headline="h", timestamp="2026-05-31T10:00:00Z", url="", body="")
        with patch("src.live.analyzer_service.utcnow") as mock_now:
            mock_now.return_value = __import__("datetime").datetime(2026, 5, 31, 11, 0, 0)
            assert svc._is_stale(event) is True

    def test_invalid_timestamp_not_stale(self, svc):
        event = NewsEvent(source="t", headline="h", timestamp="bad-date", url="", body="")
        assert svc._is_stale(event) is False


class TestOnNews:
    pytestmark = pytest.mark.asyncio

    async def test_publishes_on_high_confidence(self, bus, analyzer):
        svc = AnalyzerService(bus, analyzer=FakeAnalyzer(
            headline="good news", symbols=["AAPL"], sentiment=0.8, confidence=0.9,
        ), **DISABLE_STALE)
        await svc._on_news({"source": "t", "headline": "good news", "timestamp": "2026-05-31T10:00:00Z", "url": "", "body": ""})
        bus.publish.assert_called_once()
        call_args = bus.publish.call_args[0]
        assert call_args[0] == "sentiment"
        assert call_args[1]["sentiment"] == 0.8

    async def test_skips_low_confidence(self, bus, analyzer):
        svc = AnalyzerService(bus, analyzer=FakeAnalyzer(confidence=0.0), **DISABLE_STALE)
        await svc._on_news({"source": "t", "headline": "noise", "timestamp": "2026-05-31T10:00:00Z", "url": "", "body": ""})
        bus.publish.assert_not_called()

    async def test_passes_positions_to_analyzer(self, bus, analyzer):
        positions = {"AAPL": 10, "GOOGL": 5}
        svc = AnalyzerService(bus, analyzer=analyzer, get_positions=lambda: positions, **DISABLE_STALE)
        await svc._on_news({"source": "t", "headline": "h", "timestamp": "2026-05-31T10:00:00Z", "url": "", "body": ""})
        call_args = analyzer.analyze.call_args[0]
        assert len(call_args) == 3
        assert call_args[1] == positions
        assert call_args[2] is None

    async def test_portfolio_source_passes_positions_and_orders(self, bus, analyzer):
        class FakeSource:
            async def get_snapshot(self):
                from src.common.portfolio import OrderInfo, PortfolioSnapshot, PositionInfo
                return PortfolioSnapshot(
                    source="db", as_of=__import__("datetime").datetime(2026, 5, 31),
                    cash=1000.0,
                    positions=[PositionInfo(symbol="AAPL", qty=10), PositionInfo(symbol="XOM", qty=0)],
                    recent_orders=[OrderInfo(symbol="AAPL", action="buy", qty=10, price=200.0)],
                )

        svc = AnalyzerService(bus, analyzer=analyzer, portfolio_source=FakeSource(), **DISABLE_STALE)
        await svc._on_news({"source": "t", "headline": "h", "timestamp": "2026-05-31T10:00:00Z", "url": "", "body": ""})
        call_args = analyzer.analyze.call_args[0]
        assert call_args[1] == {"AAPL": 10}
        assert len(call_args[2]) == 1
        assert call_args[2][0].symbol == "AAPL"

    async def test_portfolio_source_failure_falls_back_to_plain(self, bus, analyzer):
        class BrokenSource:
            async def get_snapshot(self):
                raise RuntimeError("mongo down")

        analyzer._result.confidence = 0.8
        svc = AnalyzerService(bus, analyzer=analyzer, portfolio_source=BrokenSource(), **DISABLE_STALE)
        await svc._on_news({"source": "t", "headline": "h", "timestamp": "2026-05-31T10:00:00Z", "url": "", "body": ""})
        bus.publish.assert_called_once()
        call_args = analyzer.analyze.call_args[0]
        assert call_args[1] is None
        assert call_args[2] is None

    async def test_skips_stale_news(self, bus, analyzer):
        svc = AnalyzerService(bus, analyzer=analyzer, max_age_sec=10)
        with patch("src.live.analyzer_service.utcnow") as mock_now:
            mock_now.return_value = __import__("datetime").datetime(2026, 6, 1, 0, 0, 0)
            await svc._on_news({"source": "t", "headline": "old", "timestamp": "2026-05-31T10:00:00Z", "url": "", "body": ""})
        bus.publish.assert_not_called()
        analyzer.analyze.assert_not_called()

    async def test_no_positions_callable_still_works(self, bus, analyzer):
        svc = AnalyzerService(bus, analyzer=FakeAnalyzer(
            symbols=["AAPL"], sentiment=0.5, confidence=0.8,
        ), get_positions=None, **DISABLE_STALE)
        await svc._on_news({"source": "t", "headline": "h", "timestamp": "2026-05-31T10:00:00Z", "url": "", "body": ""})
        bus.publish.assert_called_once()

    async def test_start_subscribes_to_news(self, bus, analyzer):
        svc = AnalyzerService(bus, analyzer=analyzer)
        await svc.start()
        bus.subscribe.assert_called_once()
        assert bus.subscribe.call_args[0][0] == "news"
