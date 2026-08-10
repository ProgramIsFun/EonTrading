"""Unit tests for PriceMonitor — SL/TP logic, state management, entry price resolution."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.common.clock import utcnow
from src.common.trading_logic import PositionState, TradingLogic
from src.live.price_monitor import PriceMonitor


@pytest.fixture
def mock_bus():
    return MagicMock()


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.get_positions_with_prices.return_value = {}
    return store


@pytest.fixture
def logic():
    return TradingLogic(stop_loss_pct=0.1, take_profit_pct=0.1)


PRICE_PATH = "src.live.price_monitor.get_price"


class TestCheckOnceSync:
    def test_no_positions_returns_empty(self, mock_bus, mock_store, logic):
        monitor = PriceMonitor(mock_bus, mock_store, logic)
        assert monitor.check_once_sync() == []

    def test_sl_triggers_removes_state(self, mock_bus, mock_store, logic):
        monitor = PriceMonitor(mock_bus, mock_store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)

        with patch(PRICE_PATH, return_value=85):
            sold = monitor.check_once_sync()

        assert len(sold) == 1
        assert sold[0][0] == "AAPL"
        assert sold[0][1] == 90  # 100 * (1 - 0.1)
        assert "AAPL" not in monitor._states

    def test_tp_triggers_removes_state(self, mock_bus, mock_store, logic):
        monitor = PriceMonitor(mock_bus, mock_store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)

        with patch(PRICE_PATH, return_value=115):
            sold = monitor.check_once_sync()

        assert len(sold) == 1
        assert sold[0][0] == "AAPL"
        assert sold[0][1] == pytest.approx(110)  # 100 * (1 + 0.1)
        assert "AAPL" not in monitor._states

    def test_no_trigger_when_price_in_range(self, mock_bus, mock_store, logic):
        monitor = PriceMonitor(mock_bus, mock_store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)

        with patch(PRICE_PATH, return_value=105):
            sold = monitor.check_once_sync()

        assert sold == []
        assert "AAPL" in monitor._states

    def test_bad_price_skipped(self, mock_bus, mock_store, logic):
        monitor = PriceMonitor(mock_bus, mock_store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)

        with patch(PRICE_PATH, return_value=0):
            sold = monitor.check_once_sync()

        assert sold == []

    def test_trailing_sl_uses_peak(self, mock_bus, mock_store):
        logic = TradingLogic(stop_loss_pct=0.1, trailing_sl=True)
        monitor = PriceMonitor(mock_bus, mock_store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100, peak_price=120)

        with patch(PRICE_PATH, return_value=105):
            sold = monitor.check_once_sync()

        assert len(sold) == 1
        assert sold[0][1] == 108  # 120 * (1 - 0.1)

    def test_trailing_sl_persists_peak(self, mock_bus):
        logic = TradingLogic(stop_loss_pct=0.1, trailing_sl=True)
        store = MagicMock()
        store.get_positions_with_prices.return_value = {}
        monitor = PriceMonitor(mock_bus, store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100, peak_price=100)

        with patch(PRICE_PATH, return_value=108):
            monitor.check_once_sync()

        store.update_peak.assert_called_once_with("AAPL", 108)
        assert monitor._states["AAPL"].peak_price == 108

    def test_no_persist_peak_when_trailing_disabled(self, mock_bus):
        logic = TradingLogic(stop_loss_pct=0.1, trailing_sl=False)
        store = MagicMock()
        store.get_positions_with_prices.return_value = {}
        monitor = PriceMonitor(mock_bus, store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100, peak_price=100)

        with patch(PRICE_PATH, return_value=130):
            monitor.check_once_sync()

        store.update_peak.assert_not_called()

    def test_multiple_positions_one_trigger(self, mock_bus, mock_store, logic):
        monitor = PriceMonitor(mock_bus, mock_store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)
        monitor._states["GOOGL"] = PositionState("GOOGL", 5, 200)

        with patch(PRICE_PATH, side_effect=[85, 210]):
            sold = monitor.check_once_sync()

        assert len(sold) == 1
        assert sold[0][0] == "AAPL"
        assert "GOOGL" in monitor._states


class TestInit:
    def test_restores_from_store(self, mock_bus, logic):
        store = MagicMock()
        store.get_positions_with_prices.return_value = {
            "AAPL": {"entryPrice": 100, "qty": 10},
            "GOOGL": {"entryPrice": 200, "qty": 5},
        }

        monitor = PriceMonitor(mock_bus, store, logic)

        assert "AAPL" in monitor._states
        assert monitor._states["AAPL"].entry_price == 100
        assert monitor._states["AAPL"].shares == 10
        assert "GOOGL" in monitor._states

    def test_restores_peak_from_store(self, mock_bus, logic):
        store = MagicMock()
        store.get_positions_with_prices.return_value = {
            "AAPL": {"entryPrice": 100, "qty": 10, "peakPrice": 120},
        }

        monitor = PriceMonitor(mock_bus, store, logic)

        assert monitor._states["AAPL"].peak_price == 120

    def test_peak_defaults_to_entry_when_missing(self, mock_bus, logic):
        store = MagicMock()
        store.get_positions_with_prices.return_value = {
            "AAPL": {"entryPrice": 100, "qty": 10},
        }

        monitor = PriceMonitor(mock_bus, store, logic)

        assert monitor._states["AAPL"].peak_price == 100

    def test_peak_survives_restart_via_store(self, mock_bus):
        """Simulate price rising over cycles, then new monitor reads peak from store."""
        from src.common.position_store import InMemoryPositionStore

        store = InMemoryPositionStore()
        logic = TradingLogic(stop_loss_pct=0.1, trailing_sl=True)

        # Open position and create monitor
        store.open_position("AAPL", utcnow(), entry_price=100.0, qty=10)
        monitor1 = PriceMonitor(mock_bus, store, logic)
        monitor1._states["AAPL"] = PositionState("AAPL", 10, 100, peak_price=100)

        # Cycle 1: price rises to 108 — peak updates, persisted to store
        with patch(PRICE_PATH, return_value=108):
            monitor1.check_once_sync()
        assert store.get_positions_with_prices()["AAPL"]["peakPrice"] == 108

        # Cycle 2: price rises to 115 — peak updates again
        with patch(PRICE_PATH, return_value=115):
            monitor1.check_once_sync()
        assert store.get_positions_with_prices()["AAPL"]["peakPrice"] == 115

        # Simulate restart — create new monitor from same store
        monitor2 = PriceMonitor(mock_bus, store, logic)

        assert monitor2._states["AAPL"].peak_price == 115
        assert monitor2._states["AAPL"].entry_price == 100

        # New monitor uses persisted peak for SL: 115 * 0.9 = 103.5
        with patch(PRICE_PATH, return_value=103):
            sold = monitor2.check_once_sync()
        assert len(sold) == 1
        assert sold[0][1] == pytest.approx(103.5)

    def test_injects_entry_prices(self, mock_bus, mock_store, logic):
        monitor = PriceMonitor(mock_bus, mock_store, logic,
                               entry_prices={"AAPL": 100, "TSLA": 300})

        assert monitor._states["AAPL"].entry_price == 100
        assert monitor._states["TSLA"].entry_price == 300
        assert monitor._states["AAPL"].shares == 0

    def test_store_error_is_swallowed(self, mock_bus, logic):
        store = MagicMock()
        store.get_positions_with_prices.side_effect = Exception("DB down")

        monitor = PriceMonitor(mock_bus, store, logic)
        assert monitor._states == {}


class TestCheckOnceAsync:
    """Async check_once: the monitor executes its own exits via the broker."""

    @pytest.fixture
    def async_bus(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_sl_executes_and_publishes(self, async_bus, mock_store, logic):
        monitor = PriceMonitor(async_bus, mock_store, logic, broker=MagicMock())
        monitor.broker.execute = AsyncMock(return_value="ORD-1")
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)

        with patch(PRICE_PATH, return_value=90):
            sold = await monitor.check_once()

        assert sold == ["AAPL"]
        assert "AAPL" not in monitor._states
        monitor.broker.execute.assert_called_once()
        assert async_bus.publish.called
        published = async_bus.publish.call_args.args[1]
        assert published["symbol"] == "AAPL"
        assert published["action"] == "sell"
        assert published["size"] == 10

    @pytest.mark.asyncio
    async def test_failed_execution_keeps_state_for_retry(self, async_bus, mock_store, logic):
        """If the broker returns no order_id, the stop-loss state must survive."""
        monitor = PriceMonitor(async_bus, mock_store, logic, broker=MagicMock())
        monitor.broker.execute = AsyncMock(return_value=None)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)

        with patch(PRICE_PATH, return_value=90):
            sold = await monitor.check_once()

        assert sold == []
        assert "AAPL" in monitor._states, "state must be kept for retry on next tick"
        async_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_broker_error_keeps_state_for_retry(self, async_bus, mock_store, logic):
        monitor = PriceMonitor(async_bus, mock_store, logic, broker=MagicMock())
        monitor.broker.execute = AsyncMock(side_effect=RuntimeError("broker down"))
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)

        with patch(PRICE_PATH, return_value=90):
            sold = await monitor.check_once()

        assert sold == []
        assert "AAPL" in monitor._states
        async_bus.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_broker_skips_execution(self, async_bus, mock_store, logic):
        monitor = PriceMonitor(async_bus, mock_store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)

        with patch(PRICE_PATH, return_value=90):
            sold = await monitor.check_once()

        assert sold == []
        assert "AAPL" in monitor._states
        async_bus.publish.assert_not_called()


class TestRegisterEntry:
    def test_creates_new_state(self, mock_bus, mock_store, logic):
        monitor = PriceMonitor(mock_bus, mock_store, logic)
        monitor.register_entry("AAPL", 150, 20)

        assert "AAPL" in monitor._states
        assert monitor._states["AAPL"].entry_price == 150
        assert monitor._states["AAPL"].shares == 20

    def test_overwrites_existing(self, mock_bus, mock_store, logic):
        monitor = PriceMonitor(mock_bus, mock_store, logic)
        monitor._states["AAPL"] = PositionState("AAPL", 10, 100)
        monitor.register_entry("AAPL", 200, 30)

        assert monitor._states["AAPL"].entry_price == 200
        assert monitor._states["AAPL"].shares == 30
