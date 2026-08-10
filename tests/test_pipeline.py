"""Tests for the shared live pipeline assembler (build_pipeline)."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from src.common.event_bus import LocalEventBus
from src.common.events import CHANNEL_NEWS, NewsEvent
from src.common.position_store import InMemoryPositionStore
from src.common.trading_logic import TradingLogic
from src.live.pipeline import build_pipeline
from src.strategies.sentiment import KeywordSentimentAnalyzer
from tests.helpers import MockBroker


@pytest.fixture(autouse=True)
def mock_get_price():
    with patch("src.live.sentiment_trader.get_price", return_value=150.0):
        yield


@pytest.mark.asyncio
async def test_build_pipeline_assembles_standard_components():
    bus = LocalEventBus()
    await bus.start()
    try:
        broker = MockBroker()
        analyzer = KeywordSentimentAnalyzer()
        store = InMemoryPositionStore()
        logic = TradingLogic(threshold=0.3, min_confidence=0.2)

        pipeline = await build_pipeline(
            bus,
            broker=broker,
            analyzer=analyzer,
            position_store=store,
            logic=logic,
        )
        assert pipeline.trader is not None
        assert pipeline.analyzer_svc is not None
        assert pipeline.monitor is not None
        assert pipeline.monitor.logic is logic
        assert pipeline.trader.position_store is store
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_build_pipeline_handles_full_news_to_trade():
    bus = LocalEventBus()
    await bus.start()
    try:
        broker = MockBroker()
        analyzer = KeywordSentimentAnalyzer()
        store = InMemoryPositionStore()
        logic = TradingLogic(threshold=0.3, min_confidence=0.2)

        await build_pipeline(
            bus,
            broker=broker,
            analyzer=analyzer,
            position_store=store,
            logic=logic,
        )

        news = NewsEvent(
            source="test",
            headline="Apple stock surges to record high after beating earnings",
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            body="Apple reported strong growth and profit.",
        )
        await bus.publish(CHANNEL_NEWS, news.to_dict())
        await asyncio.sleep(0.2)

        assert len(broker.trades) == 1
        assert broker.trades[0].symbol == "AAPL"
        assert broker.trades[0].action == "buy"
    finally:
        await bus.stop()
