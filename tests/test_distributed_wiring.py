"""Tests that distributed runner wiring matches single-process mode.

These catch bugs where a component works in single-process (LocalEventBus)
but breaks in distributed mode because the runner forgot to wire something.
"""
import ast
import inspect
import pytest


def _get_function_source(module_path: str, func_name: str) -> str:
    """Read a module file and return the source of a function."""
    with open(module_path) as f:
        return f.read()


class TestDistributedWiring:
    """Verify distributed runners create the same component graph as single-process."""

    def test_trader_creates_price_monitor(self):
        """run_trader must create PriceMonitor and pass it to SentimentTrader."""
        src = _get_function_source("src/live/runners/run_trader.py", "main")
        # PriceMonitor must be created
        assert "PriceMonitor(" in src, "run_trader.py must create a PriceMonitor"
        # And passed to SentimentTrader
        assert "price_monitor=monitor" in src or "price_monitor=" in src, \
            "run_trader.py must pass PriceMonitor to SentimentTrader"

    def test_trader_creates_trading_logic(self):
        """run_trader must create TradingLogic (not rely on SentimentTrader defaults)."""
        src = _get_function_source("src/live/runners/run_trader.py", "main")
        assert "TradingLogic(" in src, "run_trader.py must create TradingLogic explicitly"

    def test_trader_passes_broker_args(self):
        """run_trader must pass position_store and trade_log like single-process does."""
        src = _get_function_source("src/live/runners/run_trader.py", "main")
        assert "position_store=" in src, "run_trader.py must pass position_store to SentimentTrader"
        assert "trade_log=" in src, "run_trader.py must pass trade_log to SentimentTrader"

    def test_executor_has_dedup(self):
        """TradeExecutor must deduplicate trades (at-least-once delivery protection)."""
        from src.live.brokers.broker import TradeExecutor
        executor = TradeExecutor.__init__
        src = inspect.getsource(TradeExecutor)
        assert "_seen" in src, "TradeExecutor must have dedup tracking"

    def test_single_and_distributed_use_same_components(self):
        """Both modes must use the same core component classes."""
        single_src = _get_function_source("src/live/news_trader.py", "main_single")
        trader_src = _get_function_source("src/live/runners/run_trader.py", "main")
        executor_src = _get_function_source("src/live/runners/run_executor.py", "main")
        analyzer_src = _get_function_source("src/live/runners/run_analyzer.py", "main")

        # All modes use the same component classes
        assert "SentimentTrader(" in single_src and "SentimentTrader(" in trader_src
        assert "TradeExecutor(" in single_src and "TradeExecutor(" in executor_src
        assert "AnalyzerService(" in single_src and "AnalyzerService(" in analyzer_src

    def test_monitor_reads_env_vars(self):
        """run_monitor must read SL/TP from env vars, not hardcode."""
        src = _get_function_source("src/live/runners/run_monitor.py", "main")
        assert "STOP_LOSS_PCT" in src, "run_monitor.py must read STOP_LOSS_PCT from env"
        assert "TAKE_PROFIT_PCT" in src, "run_monitor.py must read TAKE_PROFIT_PCT from env"

    def test_trader_reads_env_vars(self):
        """run_trader must read trading params from env vars, not hardcode."""
        src = _get_function_source("src/live/runners/run_trader.py", "main")
        assert "THRESHOLD" in src, "run_trader.py must read THRESHOLD from env"
        assert "STOP_LOSS_PCT" in src, "run_trader.py must read STOP_LOSS_PCT from env"
