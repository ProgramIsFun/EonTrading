"""Mock-based tests for broker implementations (FutuBroker, IBKRBroker, AlpacaBroker).

All external dependencies are mocked — no real connections needed.
"""
import asyncio
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.common.clock import utcnow
from src.common.event_bus import LocalEventBus
from src.common.events import CHANNEL_FILL, TradeEvent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_trade(symbol: str = "AAPL", action: str = "buy", price: float = 150.0) -> TradeEvent:
    return TradeEvent(
        symbol=symbol, action=action, reason="test",
        timestamp=utcnow().isoformat() + "Z", price=price, size=10,
    )


async def _collect_fills(event_bus):
    """Subscribe to fill events and return a (subscribe, get_fills) pair.

    Use:
        sub, get = await _collect_fills(event_bus)
        await sub()
        await broker.execute(...)
        fills = await get()
    """
    fills = []
    event = asyncio.Event()

    async def on_fill(msg):
        fills.append(msg)
        event.set()

    async def subscribe():
        await event_bus.subscribe(CHANNEL_FILL, on_fill)

    async def get(timeout: float = 5.0):
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return fills

    return subscribe, get


@pytest.fixture
def event_bus():
    return LocalEventBus()


# ===================================================================
# FutuBroker
# ===================================================================

def _install_futu_mock(**attrs):
    """Create + install a mock 'futu' module into sys.modules.

    Returns (mock_futu, mock_ctx) where mock_ctx is a pre-created
    OpenSecTradeContext instance you can configure further.
    """
    mock_ctx = MagicMock()
    mock_futu = MagicMock()
    mock_futu.OpenSecTradeContext.return_value = mock_ctx

    mock_futu.TrdEnv.SIMULATE = "SIMULATE"
    mock_futu.TrdEnv.REAL = "REAL"
    mock_futu.TrdSide.BUY = "BUY"
    mock_futu.TrdSide.SELL = "SELL"
    mock_futu.OrderStatus.FILLED_ALL = "FilledStatus_FILLED_ALL"
    mock_futu.OrderStatus.FILLED_PART = "FilledStatus_FILLED_PART"
    mock_futu.OrderStatus.CANCELLED_ALL = "FilledStatus_CANCELLED_ALL"
    mock_futu.OrderStatus.FAILED = "FilledStatus_FAILED"
    mock_futu.OrderStatus.DELETED = "FilledStatus_DELETED"
    mock_futu.TradeOrderHandlerBase = type("HandlerBase", (), {"on_recv_rsp": lambda self, rsp: (0, pd.DataFrame())})

    for k, v in attrs.items():
        setattr(mock_futu, k, v)

    sys.modules["futu"] = mock_futu
    return mock_futu, mock_ctx


def _remove_futu_mock():
    sys.modules.pop("futu", None)


class TestFutuBroker:

    @pytest.mark.asyncio
    async def test_execute_places_order_and_returns_id(self, event_bus):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.place_order.return_value = (0, pd.DataFrame({"order_id": ["12345"]}))

            broker = FutuBroker()
            broker.set_bus(event_bus)
            broker._ctx = mock_ctx

            order_id = await broker.execute(_make_trade())
            assert order_id == "12345"
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_execute_rejected_publishes_fill(self, event_bus):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.place_order.return_value = (1, None)

            sub, get = await _collect_fills(event_bus)
            await sub()

            broker = FutuBroker()
            broker.set_bus(event_bus)
            broker._ctx = mock_ctx

            order_id = await broker.execute(_make_trade())
            assert order_id is None
            fills = await get()
            assert len(fills) == 1
            assert fills[0]["success"] is False
            assert "rejected" in fills[0]["reason"]
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_execute_exception_publishes_fill(self, event_bus):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.place_order.side_effect = RuntimeError("connection lost")

            sub, get = await _collect_fills(event_bus)
            await sub()

            broker = FutuBroker()
            broker.set_bus(event_bus)
            broker._ctx = mock_ctx

            order_id = await broker.execute(_make_trade())
            assert order_id is None
            fills = await get()
            assert len(fills) == 1
            assert fills[0]["success"] is False
            assert "connection lost" in fills[0]["reason"]
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_check_order_filled(self):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.order_list_query.return_value = (0, pd.DataFrame({"order_status": ["FilledStatus_FILLED_ALL"]}))

            broker = FutuBroker()
            broker._ctx = mock_ctx

            status, reason = await broker.check_order("12345")
            assert status == "filled"
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_check_order_cancelled(self):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.order_list_query.return_value = (0, pd.DataFrame({"order_status": ["FilledStatus_FAILED"]}))

            broker = FutuBroker()
            broker._ctx = mock_ctx

            status, reason = await broker.check_order("12345")
            assert status == "cancelled"
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_check_order_pending(self):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.order_list_query.return_value = (0, pd.DataFrame({"order_status": ["FilledStatus_NEW"]}))

            broker = FutuBroker()
            broker._ctx = mock_ctx

            status, reason = await broker.check_order("12345")
            assert status == "pending"
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_check_order_query_error_returns_pending(self):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.order_list_query.return_value = (1, None)

            broker = FutuBroker()
            broker._ctx = mock_ctx

            status, reason = await broker.check_order("12345")
            assert status == "pending"
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_cancel_order(self):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.undo_order.return_value = (0, None)

            broker = FutuBroker()
            broker._ctx = mock_ctx

            result = await broker.cancel_order("12345")
            assert result is True
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_get_positions(self):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.position_list_query.return_value = (0, pd.DataFrame({
                "code": ["AAPL", "TSLA"],
                "qty": [100, 50],
            }))

            broker = FutuBroker()
            broker._ctx = mock_ctx

            positions = await broker.get_positions()
            assert positions == {"AAPL": 100, "TSLA": 50}
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_get_positions_error_returns_empty(self):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.position_list_query.side_effect = RuntimeError("API error")

            broker = FutuBroker()
            broker._ctx = mock_ctx

            positions = await broker.get_positions()
            assert positions == {}
        finally:
            _remove_futu_mock()

    @pytest.mark.asyncio
    async def test_get_cash(self):
        _install_futu_mock()
        try:
            from src.live.brokers.broker import FutuBroker

            mock_ctx = MagicMock()
            mock_ctx.accinfo_query.return_value = (0, pd.DataFrame({"cash": [50000.0]}))

            broker = FutuBroker()
            broker._ctx = mock_ctx

            cash = await broker.get_cash()
            assert cash == 50000.0
        finally:
            _remove_futu_mock()


# ===================================================================
# IBKRBroker
# ===================================================================

def _install_ibkr_mock():
    mock_ib = MagicMock()
    mock_ib.isConnected.return_value = True

    mock_ib_insync = MagicMock()
    mock_ib_insync.IB.return_value = mock_ib

    sys.modules["ib_insync"] = mock_ib_insync
    return mock_ib_insync, mock_ib


def _remove_ibkr_mock():
    sys.modules.pop("ib_insync", None)


class TestIBKRBroker:

    @pytest.mark.asyncio
    async def test_buy_fills_successfully(self, event_bus):
        _install_ibkr_mock()
        try:
            from src.live.brokers.broker import IBKRBroker

            mock_ib_trade = MagicMock()
            mock_ib_trade.isDone.return_value = True
            mock_ib_trade.orderStatus.status = "Filled"

            mock_ib = MagicMock()
            mock_ib.isConnected.return_value = True
            mock_ib.placeOrder.return_value = mock_ib_trade

            sub, get = await _collect_fills(event_bus)
            await sub()

            broker = IBKRBroker()
            broker._ib = mock_ib
            broker.set_bus(event_bus)

            await broker.execute(_make_trade())
            fills = await get()

            assert len(fills) == 1
            assert fills[0]["success"] is True
            assert fills[0]["symbol"] == "AAPL"
        finally:
            _remove_ibkr_mock()

    @pytest.mark.asyncio
    async def test_order_not_filled(self, event_bus):
        _install_ibkr_mock()
        try:
            from src.live.brokers.broker import IBKRBroker

            mock_ib_trade = MagicMock()
            mock_ib_trade.isDone.return_value = True
            mock_ib_trade.orderStatus.status = "Cancelled"

            mock_ib = MagicMock()
            mock_ib.isConnected.return_value = True
            mock_ib.placeOrder.return_value = mock_ib_trade

            sub, get = await _collect_fills(event_bus)
            await sub()

            broker = IBKRBroker()
            broker._ib = mock_ib
            broker.set_bus(event_bus)

            await broker.execute(_make_trade())
            fills = await get()

            assert len(fills) == 1
            assert fills[0]["success"] is False
        finally:
            _remove_ibkr_mock()

    @pytest.mark.asyncio
    async def test_exception_during_execution(self, event_bus):
        _install_ibkr_mock()
        try:
            from src.live.brokers.broker import IBKRBroker

            mock_ib = MagicMock()
            mock_ib.isConnected.side_effect = ConnectionError("TWS not running")

            sub, get = await _collect_fills(event_bus)
            await sub()

            broker = IBKRBroker()
            broker._ib = mock_ib
            broker.set_bus(event_bus)
            broker._connect = MagicMock(side_effect=ConnectionError("TWS not running"))

            await broker.execute(_make_trade())
            fills = await get()

            assert len(fills) == 1
            assert fills[0]["success"] is False
            assert "TWS not running" in fills[0]["reason"]
        finally:
            _remove_ibkr_mock()

    @pytest.mark.asyncio
    async def test_get_positions(self):
        _install_ibkr_mock()
        try:
            from src.live.brokers.broker import IBKRBroker

            mock_pos1 = MagicMock()
            mock_pos1.contract.symbol = "AAPL"
            mock_pos1.position = 100
            mock_pos2 = MagicMock()
            mock_pos2.contract.symbol = "TSLA"
            mock_pos2.position = 50

            mock_ib = MagicMock()
            mock_ib.isConnected.return_value = True
            mock_ib.positions.return_value = [mock_pos1, mock_pos2]

            broker = IBKRBroker()
            broker._ib = mock_ib

            positions = await broker.get_positions()
            assert positions == {"AAPL": 100, "TSLA": 50}
        finally:
            _remove_ibkr_mock()

    @pytest.mark.asyncio
    async def test_get_positions_error_returns_empty(self):
        _install_ibkr_mock()
        try:
            from src.live.brokers.broker import IBKRBroker

            mock_ib = MagicMock()
            mock_ib.isConnected.return_value = True
            mock_ib.positions.side_effect = RuntimeError("API error")

            broker = IBKRBroker()
            broker._ib = mock_ib

            positions = await broker.get_positions()
            assert positions == {}
        finally:
            _remove_ibkr_mock()

    @pytest.mark.asyncio
    async def test_get_cash(self):
        _install_ibkr_mock()
        try:
            from src.live.brokers.broker import IBKRBroker

            mock_av1 = MagicMock()
            mock_av1.tag = "CashBalance"
            mock_av1.currency = "USD"
            mock_av1.value = "75000.50"
            mock_av2 = MagicMock()
            mock_av2.tag = "CashBalance"
            mock_av2.currency = "EUR"
            mock_av2.value = "50000"

            mock_ib = MagicMock()
            mock_ib.isConnected.return_value = True
            mock_ib.accountValues.return_value = [mock_av1, mock_av2]

            broker = IBKRBroker()
            broker._ib = mock_ib

            cash = await broker.get_cash()
            assert cash == 75000.50
        finally:
            _remove_ibkr_mock()

    @pytest.mark.asyncio
    async def test_get_cash_error_returns_zero(self):
        _install_ibkr_mock()
        try:
            from src.live.brokers.broker import IBKRBroker

            mock_ib = MagicMock()
            mock_ib.isConnected.return_value = True
            mock_ib.accountValues.side_effect = RuntimeError("API error")

            broker = IBKRBroker()
            broker._ib = mock_ib

            cash = await broker.get_cash()
            assert cash == 0.0
        finally:
            _remove_ibkr_mock()


# ===================================================================
# AlpacaBroker
# ===================================================================

def _install_alpaca_mock():
    mock_alpaca = MagicMock()
    sys.modules["alpaca_trade_api"] = mock_alpaca
    return mock_alpaca


def _remove_alpaca_mock():
    sys.modules.pop("alpaca_trade_api", None)


class TestAlpacaBroker:

    @pytest.mark.asyncio
    async def test_buy_fills_successfully(self, event_bus):
        _install_alpaca_mock()
        try:
            from src.live.brokers.broker import AlpacaBroker

            mock_order = MagicMock()
            mock_order.id = "order-123"
            mock_order.status = "filled"

            mock_api = MagicMock()
            mock_api.submit_order.return_value = mock_order
            mock_api.get_order.return_value = mock_order

            sub, get = await _collect_fills(event_bus)
            await sub()

            broker = AlpacaBroker(api_key="test", secret_key="test", paper=True)
            broker._api = mock_api
            broker.set_bus(event_bus)

            await broker.execute(_make_trade())
            fills = await get()

            assert len(fills) == 1
            assert fills[0]["success"] is True
            assert fills[0]["symbol"] == "AAPL"
        finally:
            _remove_alpaca_mock()

    @pytest.mark.asyncio
    async def test_order_cancelled(self, event_bus):
        _install_alpaca_mock()
        try:
            from src.live.brokers.broker import AlpacaBroker

            mock_order = MagicMock()
            mock_order.id = "order-123"
            mock_order.status = "canceled"

            mock_api = MagicMock()
            mock_api.submit_order.return_value = mock_order
            mock_api.get_order.return_value = mock_order

            sub, get = await _collect_fills(event_bus)
            await sub()

            broker = AlpacaBroker(api_key="test", secret_key="test", paper=True)
            broker._api = mock_api
            broker.set_bus(event_bus)

            await broker.execute(_make_trade())
            fills = await get()

            assert len(fills) == 1
            assert fills[0]["success"] is False
        finally:
            _remove_alpaca_mock()

    @pytest.mark.asyncio
    async def test_timeout(self, event_bus):
        _install_alpaca_mock()
        try:
            from unittest.mock import patch
            # AlpacaBroker.execute polls 30× with await asyncio.sleep(2) to not spam Alpaca's API.
            # In this test all calls are mocked, so the sleep is just 60s of dead time.
            patcher = patch("asyncio.sleep", return_value=None)
            patcher.start()
            from src.live.brokers.broker import AlpacaBroker

            mock_order = MagicMock()
            mock_order.id = "order-123"
            mock_order.status = "new"

            mock_api = MagicMock()
            mock_api.submit_order.return_value = mock_order
            mock_api.get_order.return_value = mock_order

            sub, get = await _collect_fills(event_bus)
            await sub()

            broker = AlpacaBroker(api_key="test", secret_key="test", paper=True)
            broker._api = mock_api
            broker.set_bus(event_bus)

            await broker.execute(_make_trade())
            fills = await get()

            assert len(fills) == 1
            assert fills[0]["success"] is False
            assert fills[0]["reason"] == "timeout"
        finally:
            patcher.stop()
            _remove_alpaca_mock()

    @pytest.mark.asyncio
    async def test_exception_during_execution(self, event_bus):
        _install_alpaca_mock()
        try:
            from src.live.brokers.broker import AlpacaBroker

            mock_api = MagicMock()
            mock_api.submit_order.side_effect = RuntimeError("API rate limited")

            sub, get = await _collect_fills(event_bus)
            await sub()

            broker = AlpacaBroker(api_key="test", secret_key="test", paper=True)
            broker._api = mock_api
            broker.set_bus(event_bus)

            await broker.execute(_make_trade())
            fills = await get()

            assert len(fills) == 1
            assert fills[0]["success"] is False
            assert "rate limited" in fills[0]["reason"]
        finally:
            _remove_alpaca_mock()

    @pytest.mark.asyncio
    async def test_get_positions(self):
        _install_alpaca_mock()
        try:
            from src.live.brokers.broker import AlpacaBroker

            mock_pos1 = MagicMock()
            mock_pos1.symbol = "AAPL"
            mock_pos1.qty = 100
            mock_pos2 = MagicMock()
            mock_pos2.symbol = "TSLA"
            mock_pos2.qty = 50

            mock_api = MagicMock()
            mock_api.list_positions.return_value = [mock_pos1, mock_pos2]

            broker = AlpacaBroker(api_key="test", secret_key="test", paper=True)
            broker._api = mock_api

            positions = await broker.get_positions()
            assert positions == {"AAPL": 100, "TSLA": 50}
        finally:
            _remove_alpaca_mock()

    @pytest.mark.asyncio
    async def test_get_positions_error_returns_empty(self):
        _install_alpaca_mock()
        try:
            from src.live.brokers.broker import AlpacaBroker

            mock_api = MagicMock()
            mock_api.list_positions.side_effect = RuntimeError("API error")

            broker = AlpacaBroker(api_key="test", secret_key="test", paper=True)
            broker._api = mock_api

            positions = await broker.get_positions()
            assert positions == {}
        finally:
            _remove_alpaca_mock()

    @pytest.mark.asyncio
    async def test_get_cash(self):
        _install_alpaca_mock()
        try:
            from src.live.brokers.broker import AlpacaBroker

            mock_api = MagicMock()
            mock_api.get_account.return_value = MagicMock(cash="100000.25")

            broker = AlpacaBroker(api_key="test", secret_key="test", paper=True)
            broker._api = mock_api

            cash = await broker.get_cash()
            assert cash == 100000.25
        finally:
            _remove_alpaca_mock()

    @pytest.mark.asyncio
    async def test_get_cash_error_returns_zero(self):
        _install_alpaca_mock()
        try:
            from src.live.brokers.broker import AlpacaBroker

            mock_api = MagicMock()
            mock_api.get_account.side_effect = RuntimeError("API error")

            broker = AlpacaBroker(api_key="test", secret_key="test", paper=True)
            broker._api = mock_api

            cash = await broker.get_cash()
            assert cash == 0.0
        finally:
            _remove_alpaca_mock()
