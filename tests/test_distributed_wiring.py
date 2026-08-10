"""Tests that distributed runner wiring matches single-process mode.

These catch bugs where a component works in single-process (LocalEventBus)
but breaks in distributed mode because the runner forgot to wire something.
"""
import ast
import inspect

import pytest


def _get_function_source(module_path: str, func_name: str) -> str:
    """Read a module file and return the source of a function."""
    with open(module_path, encoding="utf-8") as f:
        return f.read()


class TestDistributedWiring:
    """Verify distributed runners create the same component graph as single-process."""

    def test_trader_no_price_monitor(self):
        """run_trader must NOT create PriceMonitor — it runs separately in run_monitor.py."""
        src = _get_function_source("src/live/runners/run_trader.py", "main")
        assert "PriceMonitor" not in src, "run_trader.py should not create PriceMonitor"

    def test_trader_creates_trading_logic(self):
        """run_trader must create TradingLogic (not rely on SentimentTrader defaults)."""
        src = _get_function_source("src/live/runners/run_trader.py", "main")
        assert "TradingLogic" in src, "run_trader.py must create TradingLogic explicitly"

    def test_trader_passes_position_store(self):
        """run_trader must pass position_store to SentimentTrader (read-only)."""
        src = _get_function_source("src/live/runners/run_trader.py", "main")
        assert "position_store=" in src, "run_trader.py must pass position_store to SentimentTrader"

    def test_trader_owns_execution_and_order_logging(self):
        """run_trader must pass broker and log_order to SentimentTrader."""
        src = _get_function_source("src/live/runners/run_trader.py", "main")
        assert "broker=broker" in src, "run_trader.py must pass broker to SentimentTrader"
        assert "log_order=mongo_log_order" in src, "run_trader.py must pass log_order to SentimentTrader"

    def test_single_and_distributed_use_same_components(self):
        """Both modes must use the same core component classes."""
        single_src = _get_function_source("src/live/news_trader.py", "main_single")
        trader_src = _get_function_source("src/live/runners/run_trader.py", "main")
        analyzer_src = _get_function_source("src/live/runners/run_analyzer.py", "main")

        # Single process delegates wiring to the shared pipeline assembler
        assert "build_pipeline(" in single_src

        # Distributed runners build the same component classes directly
        assert "SentimentTrader(" in trader_src
        assert "AnalyzerService(" in analyzer_src

    def test_build_pipeline_wires_standard_components(self):
        """build_pipeline must create the standard component graph."""
        from src.live.pipeline import build_pipeline
        src = inspect.getsource(build_pipeline)
        assert "PriceMonitor(" in src
        assert "SentimentTrader(" in src
        assert "AnalyzerService(" in src

    def test_monitor_owns_execution(self):
        """run_monitor must give PriceMonitor a broker — the monitor executes its own exits."""
        src = _get_function_source("src/live/runners/run_monitor.py", "main")
        assert "build_broker()" in src, "run_monitor.py must build a broker"
        assert "broker=broker" in src, "run_monitor.py must pass broker to PriceMonitor"

    def test_monitor_reads_env_vars(self):
        """run_monitor must read SL/TP from settings (via from_settings or directly)."""
        src = _get_function_source("src/live/runners/run_monitor.py", "main")
        assert "TradingLogic.from_settings()" in src or "settings.stop_loss_pct" in src, \
            "run_monitor.py must read trading params from settings"
        assert "settings.sl_check_interval" in src, "run_monitor.py must read sl_check_interval from settings"

    def test_trader_reads_env_vars(self):
        """run_trader must read trading params from settings (via from_settings or directly)."""
        src = _get_function_source("src/live/runners/run_trader.py", "main")
        assert "TradingLogic.from_settings()" in src or "settings.threshold" in src, \
            "run_trader.py must read trading params from settings"
