"""Shared test helpers: MockBroker, FakePositionStore, Collector, parse_trade."""
import asyncio
from uuid import uuid4

from src.common.events import TradeEvent
from src.common.position_store import InMemoryPositionStore
from src.live.brokers import Broker


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


# Re-export InMemoryPositionStore as FakePositionStore for backward compatibility.
# All tests should use InMemoryPositionStore directly in new code.
FakePositionStore = InMemoryPositionStore


class Collector:
    """Async subscriber helper that collects messages and signals via asyncio.Event.

    Usage:
        collector = Collector()
        await bus.subscribe("trade", collector.handler)
        await bus.publish("trade", {"symbol": "AAPL"})
        ok = await collector.wait_for_count(1)
        assert collector.items[0]["symbol"] == "AAPL"
    """

    def __init__(self, parser=None, on_message=None):
        self.items = []
        self._parser = parser or (lambda x: x)
        self._on_message = on_message
        self._event = asyncio.Event()
        self._target: int | None = None

    @property
    def handler(self):
        async def _handler(msg):
            parsed = self._parser(msg)
            self.items.append(parsed)
            if self._on_message:
                self._on_message(parsed)
            if self._target is not None and len(self.items) >= self._target:
                self._event.set()
        return _handler

    async def wait_for_count(self, n: int, timeout: float = 5.0) -> bool:
        if len(self.items) >= n:
            return True
        self._target = n
        self._event.clear()
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        finally:
            self._target = None
        return len(self.items) >= n


def parse_trade(msg):
    return TradeEvent.from_dict(msg)
