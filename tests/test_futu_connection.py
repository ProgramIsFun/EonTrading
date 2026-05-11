"""Integration test: Futu OpenD paper trading connection.

Requires OpenD running on 127.0.0.1:11111.
Run with: pytest -m futu
"""
import asyncio

import pytest

pytest.importorskip("futu")

pytestmark = pytest.mark.futu


@pytest.fixture
def broker():
    from src.live.brokers.broker import FutuBroker

    return FutuBroker(host="127.0.0.1", port=11111, simulate=True, confirm_mode="poll")


@pytest.fixture
def fast_broker():
    from src.live.brokers.broker import FutuBroker

    return FutuBroker(
        host="127.0.0.1", port=11111, simulate=True,
        confirm_mode="poll", poll_interval=0.5, poll_timeout=15.0,
    )


@pytest.mark.asyncio
async def test_get_cash(broker):
    cash = await broker.get_cash()
    assert isinstance(cash, float)
    assert cash > 0


@pytest.mark.asyncio
async def test_get_positions(broker):
    positions = await broker.get_positions()
    assert isinstance(positions, dict)
    for code, qty in positions.items():
        assert isinstance(code, str)
        assert isinstance(qty, int)
        assert qty > 0


@pytest.mark.asyncio
async def test_buy_and_sell(fast_broker):
    from src.common.event_bus import LocalEventBus
    from src.common.events import CHANNEL_FILL

    SYMBOL = "HK.00700"
    QTY = 100
    PRICE = 500.0

    # --- Before ---
    cash_before = await fast_broker.get_cash()
    positions_before = await fast_broker.get_positions()
    pos_before = positions_before.get(SYMBOL, 0)

    # --- Set up bus + fill collector ---
    bus = LocalEventBus()
    fast_broker.set_bus(bus)
    fills = []
    event = asyncio.Event()

    async def on_fill(msg):
        fills.append(msg)
        event.set()

    await bus.subscribe(CHANNEL_FILL, on_fill)

    # --- Buy 1 share ---
    from src.common.events import TradeEvent
    from src.common.clock import utcnow

    trade = TradeEvent(
        symbol=SYMBOL, action="buy", reason="integration test",
        timestamp=utcnow().isoformat() + "Z", price=PRICE, size=QTY,
    )
    await fast_broker.execute(trade)
    await asyncio.wait_for(event.wait(), timeout=20.0)

    assert len(fills) == 1
    assert fills[0]["success"] is True, f"Buy failed: {fills[0].get('reason', '')}"
    assert fills[0]["symbol"] == SYMBOL
    assert fills[0]["action"] == "buy"

    # --- Verify cash decreased / position increased ---
    cash_mid = await fast_broker.get_cash()
    positions_mid = await fast_broker.get_positions()
    pos_mid = positions_mid.get(SYMBOL, 0)

    assert cash_mid < cash_before, "Cash should decrease after buy"
    assert pos_mid == pos_before + QTY, f"Position should increase by {QTY}"

    # --- Reset fill collector ---
    fills.clear()
    event.clear()

    # --- Sell back ---
    trade = TradeEvent(
        symbol=SYMBOL, action="sell", reason="integration test revert",
        timestamp=utcnow().isoformat() + "Z", price=1.0, size=QTY,
    )
    await fast_broker.execute(trade)
    await asyncio.wait_for(event.wait(), timeout=20.0)

    assert len(fills) == 1
    assert fills[0]["success"] is True, f"Sell failed: {fills[0].get('reason', '')}"
    assert fills[0]["symbol"] == SYMBOL
    assert fills[0]["action"] == "sell"

    # --- Verify cash / position returned ---
    cash_after = await fast_broker.get_cash()
    positions_after = await fast_broker.get_positions()
    pos_after = positions_after.get(SYMBOL, 0)

    assert pos_after == pos_before, f"Position should return to {pos_before}, got {pos_after}"

    cash_diff = abs(cash_after - cash_before)
    assert cash_diff < 200.0, \
        f"Cash diff too large after round-trip: {cash_diff:.2f}"
