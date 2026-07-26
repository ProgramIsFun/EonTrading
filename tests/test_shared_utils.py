"""Tests for shared utilities: compute_backtest_metrics, BacktestResultBase, Broker._safe, FakePositionStore."""
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.backtest.engine import BacktestResult, BacktestResultBase, Trade, compute_backtest_metrics
from src.common.position_store import InMemoryPositionStore
from src.live.brokers.broker import Broker, FillStatus


# ---------------------------------------------------------------------------
# compute_backtest_metrics
# ---------------------------------------------------------------------------

class TestComputeBacktestMetrics:

    def test_basic_metrics(self):
        equity = [10000, 10500, 11000, 10800, 11200]
        trades = [MagicMock(pnl=200), MagicMock(pnl=-100), MagicMock(pnl=300)]
        result = compute_backtest_metrics(equity, 10000, trades)

        assert result["final_value"] == 11200
        assert result["total_return_pct"] == pytest.approx(12.0)
        assert result["total_trades"] == 3
        assert result["win_rate"] == pytest.approx(2 / 3 * 100)
        assert isinstance(result["equity_curve"], pd.Series)
        assert len(result["equity_curve"]) == 5

    def test_empty_equity(self):
        result = compute_backtest_metrics([], 10000, [])
        assert result["final_value"] == 10000
        assert result["total_return_pct"] == 0
        assert result["max_drawdown_pct"] == 0
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0

    def test_no_trades(self):
        equity = [10000, 10000, 10000]
        result = compute_backtest_metrics(equity, 10000, [])
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0

    def test_all_winning_trades(self):
        trades = [MagicMock(pnl=100), MagicMock(pnl=200), MagicMock(pnl=50)]
        result = compute_backtest_metrics([10000, 10350], 10000, trades)
        assert result["win_rate"] == 100.0

    def test_all_losing_trades(self):
        trades = [MagicMock(pnl=-100), MagicMock(pnl=-200)]
        result = compute_backtest_metrics([10000, 9700], 10000, trades)
        assert result["win_rate"] == 0.0

    def test_max_drawdown(self):
        # Peak at 12000, trough at 8000 → 33.33% drawdown
        equity = [10000, 12000, 8000, 10000]
        result = compute_backtest_metrics(equity, 10000, [])
        assert result["max_drawdown_pct"] == pytest.approx(33.33, abs=0.01)

    def test_zero_capital(self):
        result = compute_backtest_metrics([0, 0], 0, [])
        assert result["total_return_pct"] == 0
        assert result["final_value"] == 0

    def test_custom_wins_filter(self):
        trades = [
            MagicMock(pnl=100, action="buy"),
            MagicMock(pnl=-50, action="sell"),
            MagicMock(pnl=200, action="sell"),
        ]
        result = compute_backtest_metrics(
            [10000, 10250], 10000, trades,
            wins_filter=lambda t: [x for x in t if x.action == "sell"],
        )
        # 2 sell trades, 1 win → 50%
        assert result["win_rate"] == 50.0
        assert result["total_trades"] == 3  # total_trades counts all trades

    def test_custom_index(self):
        idx = pd.date_range("2025-01-01", periods=3, freq="D")
        result = compute_backtest_metrics([100, 110, 105], 100, [], index=idx)
        assert list(result["equity_curve"].index) == list(idx)

    def test_monotonically_rising_no_drawdown(self):
        equity = list(range(100, 200))
        result = compute_backtest_metrics(equity, 100, [])
        assert result["max_drawdown_pct"] == 0

    def test_monotonically_falling(self):
        equity = list(range(200, 99, -1))
        result = compute_backtest_metrics(equity, 200, [])
        assert result["max_drawdown_pct"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# BacktestResultBase
# ---------------------------------------------------------------------------

class TestBacktestResultBase:

    def test_summary_contains_key_info(self):
        r = BacktestResultBase(
            initial_capital=10000, final_value=12000,
            total_return_pct=20.0, max_drawdown_pct=5.0,
            total_trades=10, win_rate=60.0,
        )
        s = r.summary()
        assert "20.00%" in s
        assert "5.00%" in s
        assert "10" in s
        assert "60.0%" in s
        assert "$12,000" in s

    def test_inheritance_compatibility(self):
        """BacktestResult should be usable wherever BacktestResultBase is expected."""
        r = BacktestResult(
            strategy="SMA", symbol="AAPL",
            initial_capital=10000, final_value=11000,
            total_return_pct=10.0, max_drawdown_pct=3.0,
            total_trades=5, win_rate=60.0,
        )
        assert isinstance(r, BacktestResultBase)
        assert r.strategy == "SMA"
        assert r.symbol == "AAPL"

    def test_defaults(self):
        r = BacktestResultBase(
            initial_capital=10000, final_value=10000,
            total_return_pct=0, max_drawdown_pct=0,
            total_trades=0, win_rate=0,
        )
        assert r.trades == []
        assert len(r.equity_curve) == 0

    def test_result_from_metrics_dict(self):
        """Verify compute_backtest_metrics output can unpack into BacktestResultBase."""
        metrics = compute_backtest_metrics([10000, 11000], 10000, [MagicMock(pnl=1000)])
        r = BacktestResultBase(initial_capital=10000, **metrics, trades=[MagicMock(pnl=1000)])
        assert r.final_value == 11000
        assert r.total_return_pct == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Broker._safe
# ---------------------------------------------------------------------------

class TestBrokerSafe:

    @pytest.mark.asyncio
    async def test_safe_calls_connect(self):
        class TestBrokerImpl(Broker):
            def __init__(self):
                self.connect_called = False
            def _connect(self):
                self.connect_called = True
            async def execute(self, trade):
                pass
            async def get_positions(self):
                return {}

        broker = TestBrokerImpl()
        async with broker._safe("test_op"):
            pass
        assert broker.connect_called

    @pytest.mark.asyncio
    async def test_safe_logs_and_reraises_on_error(self):
        class FailingBroker(Broker):
            def _connect(self):
                pass
            async def execute(self, trade):
                pass
            async def get_positions(self):
                return {}

        broker = FailingBroker()
        with pytest.raises(RuntimeError, match="boom"):
            async with broker._safe("failing_op"):
                raise RuntimeError("boom")

    @pytest.mark.asyncio
    async def test_safe_logs_error_message(self, caplog):
        class ErrorBroker(Broker):
            def _connect(self):
                pass
            async def execute(self, trade):
                pass
            async def get_positions(self):
                return {}

        broker = ErrorBroker()
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError):
                async with broker._safe("my_operation"):
                    raise ValueError("test error")

        assert any("my_operation" in record.message for record in caplog.records)
        assert any("test error" in record.message for record in caplog.records)

    @pytest.mark.asyncio
    async def test_safe_returns_from_body(self):
        class SimpleBroker(Broker):
            def _connect(self):
                pass
            async def execute(self, trade):
                pass
            async def get_positions(self):
                return {}

        broker = SimpleBroker()
        async with broker._safe("op"):
            result = 42
        # The context manager doesn't capture return values, but the body executes
        assert result == 42


# ---------------------------------------------------------------------------
# FakePositionStore re-export
# ---------------------------------------------------------------------------

class TestFakePositionStoreReexport:

    def test_fake_position_store_is_in_memory(self):
        from tests.helpers import FakePositionStore
        assert FakePositionStore is InMemoryPositionStore

    def test_fake_position_store_has_expected_methods(self):
        from tests.helpers import FakePositionStore
        store = FakePositionStore()
        assert hasattr(store, "get_positions")
        assert hasattr(store, "get_positions_with_prices")
        assert hasattr(store, "open_position")
        assert hasattr(store, "close_position")
        assert hasattr(store, "set_positions")

    def test_fake_position_store_works_like_in_memory(self):
        from tests.helpers import FakePositionStore
        from datetime import datetime

        store = FakePositionStore()
        now = datetime(2025, 1, 1, 12, 0, 0)

        store.open_position("AAPL", now, entry_price=150.0, qty=10)
        positions = store.get_positions()
        assert "AAPL" in positions

        with_prices = store.get_positions_with_prices()
        assert with_prices["AAPL"]["entryPrice"] == 150.0
        assert with_prices["AAPL"]["qty"] == 10

        store.close_position("AAPL")
        assert "AAPL" not in store.get_positions()
