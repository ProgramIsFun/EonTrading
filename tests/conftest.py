"""Shared test fixtures.

All tests mock MongoDB. If complex queries or aggregations are added, consider a real test DB.
"""
from uuid import uuid4

import pytest

from src.common.event_bus import LocalEventBus
from src.common.events import TradeEvent
from src.live.brokers.broker import Broker


class MockBroker(Broker):
    """Broker that records trades and returns synthetic order_id."""

    def __init__(self):
        self.trades: list[TradeEvent] = []

    async def execute(self, trade: TradeEvent) -> str:
        self.trades.append(trade)
        return f"mock-{trade.symbol}-{uuid4().hex[:8]}"

    async def check_order(self, order_id: str) -> tuple[str, str | None]:
        return ("filled", None)

    async def get_positions(self) -> dict[str, int]:
        return {}


@pytest.fixture
def event_bus():
    return LocalEventBus()


@pytest.fixture
def mock_broker():
    return MockBroker()
