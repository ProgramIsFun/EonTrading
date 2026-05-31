"""Unit tests for PriceMonitor — SL/TP logic, state management, entry price resolution."""
from unittest.mock import MagicMock, patch

import pytest

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


PRICE_PATH = "src.common.price.get_price"


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
