"""Integration test: Futu OpenD paper trading connection.

Requires OpenD running on 127.0.0.1:11111.
Run with: pytest -m futu
"""
import pytest

pytest.importorskip("futu")

pytestmark = pytest.mark.futu


@pytest.fixture
def broker():
    from src.live.brokers.broker import FutuBroker

    return FutuBroker(host="127.0.0.1", port=11111, simulate=True, confirm_mode="poll")


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
async def test_buy(broker):
    from src.common.events import TradeEvent
    from src.common.clock import utcnow

    SYMBOL = "HK.00700"
    QTY = 100
    trade = TradeEvent(
        symbol=SYMBOL, action="buy", reason="integration test",
        timestamp=utcnow().isoformat() + "Z", price=500.0, size=QTY,
    )
    order_id = await broker.execute(trade)
    assert order_id is not None, "Buy order was not accepted by Futu"


@pytest.mark.asyncio
async def test_sell(broker):
    from src.common.events import TradeEvent
    from src.common.clock import utcnow

    SYMBOL = "HK.00700"
    QTY = 100
    trade = TradeEvent(
        symbol=SYMBOL, action="sell", reason="integration test",
        timestamp=utcnow().isoformat() + "Z", price=1.0, size=QTY,
    )
    order_id = await broker.execute(trade)
    assert order_id is not None, "Sell order was not accepted by Futu"
