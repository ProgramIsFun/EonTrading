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
