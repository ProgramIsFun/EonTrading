"""Shared test fixtures.

All tests mock MongoDB. If complex queries or aggregations are added, consider a real test DB.
"""
import pytest
from src.common.event_bus import LocalEventBus
from src.common.events import TradeEvent
from src.live.brokers.broker import Broker


class MockBroker(Broker):
    """Broker that records trades and auto-fills them."""

    def __init__(self):
        self.trades: list[TradeEvent] = []

    async def execute(self, trade: TradeEvent):
        self.trades.append(trade)
        await self._publish_fill(trade.symbol, trade.action, True, "filled (mock)")

    async def get_positions(self) -> dict[str, int]:
        return {}


@pytest.fixture
def event_bus():
    return LocalEventBus()


@pytest.fixture
def mock_broker():
    return MockBroker()
