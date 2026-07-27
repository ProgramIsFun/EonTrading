"""Tests for distributed runner scripts.

Verifies each runner:
- Uses runner_lifecycle for bus/heartbeat/banner/shutdown
- Builds the correct component
- Passes a unique group name
- Handles shutdown gracefully
"""
import ast
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


RUNNERS = {
    "watcher": "src/live/runners/run_watcher.py",
    "analyzer": "src/live/runners/run_analyzer.py",
    "trader": "src/live/runners/run_trader.py",
    "executor": "src/live/runners/run_executor.py",
    "monitor": "src/live/runners/run_monitor.py",
    "order_tracker": "src/live/runners/run_order_tracker.py",
    "wealth": "src/live/runners/run_wealth.py",
}

EXPECTED_GROUPS = {
    "watcher": "newswatcher",
    "analyzer": "analyzer",
    "trader": "trader",
    "executor": "executor",
    "monitor": "monitor",
    "order_tracker": "order_tracker",
    "wealth": "wealth",
}

_LIFECYCLE_PATCHES = [
    "src.common.event_bus.RedisStreamBus",
    "src.common.heartbeat.Heartbeat",
    "src.common.startup.banner",
]


def _read_source(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


# ── Structural tests (AST-based, no imports needed) ──────────────────────

class TestRunnerStructure:
    """Verify each runner uses runner_lifecycle correctly."""

    @pytest.mark.parametrize("name,path", RUNNERS.items())
    def test_has_main_function(self, name, path):
        tree = ast.parse(_read_source(path))
        funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)]
        assert "main" in funcs, f"run_{name}.py must define async def main()"

    @pytest.mark.parametrize("name,path", RUNNERS.items())
    def test_imports_runner_lifecycle(self, name, path):
        src = _read_source(path)
        assert "from src.live.runners import runner_lifecycle" in src

    @pytest.mark.parametrize("name,path", RUNNERS.items())
    def test_uses_runner_lifecycle_context(self, name, path):
        src = _read_source(path)
        assert "async with runner_lifecycle(" in src

    @pytest.mark.parametrize("name,path", RUNNERS.items())
    def test_waits_for_shutdown(self, name, path):
        src = _read_source(path)
        assert "create_shutdown_event()" in src

    @pytest.mark.parametrize("name,path", RUNNERS.items())
    def test_has_if_main_guard(self, name, path):
        src = _read_source(path)
        assert 'if __name__ == "__main__"' in src

    @pytest.mark.parametrize("name,path", RUNNERS.items())
    def test_runs_with_asyncio_run(self, name, path):
        src = _read_source(path)
        assert "asyncio.run(main())" in src

    @pytest.mark.parametrize("name,path", RUNNERS.items())
    def test_sets_up_logging(self, name, path):
        src = _read_source(path)
        assert "setup_logging(" in src


class TestRunnerGroupNames:
    """Each runner passes a distinct group name to runner_lifecycle."""

    @pytest.mark.parametrize("name,path", RUNNERS.items())
    def test_passes_correct_group_name(self, name, path):
        src = _read_source(path)
        expected = EXPECTED_GROUPS[name]
        assert f'runner_lifecycle("{expected}"' in src

    def test_all_groups_unique(self):
        assert len(set(EXPECTED_GROUPS.values())) == len(EXPECTED_GROUPS)


class TestRunnerComponents:
    """Each runner builds the correct component class."""

    def test_watcher_creates_news_watcher(self):
        assert "NewsWatcher(" in _read_source(RUNNERS["watcher"])

    def test_analyzer_creates_analyzer_service(self):
        assert "AnalyzerService(" in _read_source(RUNNERS["analyzer"])

    def test_trader_creates_sentiment_trader(self):
        assert "SentimentTrader(" in _read_source(RUNNERS["trader"])

    def test_executor_creates_trade_executor(self):
        assert "TradeExecutor(" in _read_source(RUNNERS["executor"])

    def test_monitor_creates_price_monitor(self):
        assert "PriceMonitor(" in _read_source(RUNNERS["monitor"])

    def test_order_tracker_creates_order_tracker(self):
        assert "OrderTracker(" in _read_source(RUNNERS["order_tracker"])


# ── Lifecycle helper tests ──────────────────────────────────────────────

class TestRunnerLifecycle:
    """Test the shared runner_lifecycle context manager."""

    @pytest.mark.asyncio
    async def test_creates_bus_starts_and_stops(self):
        from src.live.runners import runner_lifecycle

        mock_bus = AsyncMock()
        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat"), \
             patch("src.common.startup.banner"):
            async with runner_lifecycle("test", "Test", {}) as bus:
                assert bus is mock_bus
                mock_bus.start.assert_called_once()
            mock_bus.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_creates_heartbeat_with_metadata(self):
        from src.live.runners import runner_lifecycle

        mock_bus = AsyncMock()
        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat") as mock_hb, \
             patch("src.common.startup.banner"):
            async with runner_lifecycle("test", "Test", {}, heartbeat_metadata={"k": "v"}):
                pass
            mock_hb.create_background.assert_called_once_with("test", metadata={"k": "v"})

    @pytest.mark.asyncio
    async def test_default_heartbeat_metadata(self):
        from src.live.runners import runner_lifecycle

        mock_bus = AsyncMock()
        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat") as mock_hb, \
             patch("src.common.startup.banner"):
            async with runner_lifecycle("test", "Test", {}):
                pass
            mock_hb.create_background.assert_called_once_with("test", metadata={"mode": "distributed"})

    @pytest.mark.asyncio
    async def test_calls_banner(self):
        from src.live.runners import runner_lifecycle

        mock_bus = AsyncMock()
        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat"), \
             patch("src.common.startup.banner") as mock_banner:
            async with runner_lifecycle("test", "MyTitle", {"key": "val"}):
                pass
            mock_banner.assert_called_once_with("MyTitle", {"key": "val"})


# ── Runtime tests (execute main() with mocked deps) ──────────────────────

class TestRunnerMainExecution:
    """Run each runner's main() with mocked lifecycle + component deps.

    Lifecycle deps (bus, heartbeat, banner) are patched at src.common.*
    since runner_lifecycle does deferred imports. Component-specific deps
    are patched on the runner module.
    """

    @pytest.mark.asyncio
    async def test_analyzer_runner_wiring(self):
        import src.live.runners.run_analyzer as mod

        mock_bus = AsyncMock()
        mock_store = MagicMock()
        mock_store.get_positions = MagicMock(return_value={})

        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat") as mock_hb, \
             patch("src.common.startup.banner"), \
             patch.object(mod, "PositionStore", return_value=mock_store), \
             patch.object(mod, "build_analyzer") as mock_build, \
             patch.object(mod, "AnalyzerService") as mock_svc, \
             patch.object(mod, "create_shutdown_event") as mock_shutdown:
            mock_build.return_value = (MagicMock(name="analyzer"), "keyword")
            mock_svc.return_value = AsyncMock()
            evt = asyncio.Event()
            evt.set()
            mock_shutdown.return_value = evt

            await mod.main()

            mock_bus.start.assert_called_once()
            mock_bus.stop.assert_called_once()
            mock_hb.create_background.assert_called_once()
            assert mock_hb.create_background.call_args[0][0] == "analyzer"
            mock_svc.return_value.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_executor_runner_wiring(self):
        import src.live.runners.run_executor as mod

        mock_bus = AsyncMock()
        mock_broker = MagicMock()

        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat") as mock_hb, \
             patch("src.common.startup.banner"), \
             patch.object(mod, "build_broker", return_value=mock_broker), \
             patch.object(mod, "TradeExecutor") as mock_exec, \
             patch.object(mod, "create_shutdown_event") as mock_shutdown, \
             patch.object(mod, "mongo_log_order"):
            mock_exec.return_value = AsyncMock()
            evt = asyncio.Event()
            evt.set()
            mock_shutdown.return_value = evt

            await mod.main()

            mock_bus.start.assert_called_once()
            mock_bus.stop.assert_called_once()
            mock_hb.create_background.assert_called_once()
            mock_exec.return_value.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_trader_runner_wiring(self):
        import src.live.runners.run_trader as mod

        mock_bus = AsyncMock()
        mock_store = MagicMock()
        mock_broker = MagicMock()

        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat") as mock_hb, \
             patch("src.common.startup.banner"), \
             patch.object(mod, "build_broker", return_value=mock_broker), \
             patch.object(mod, "PositionStore", return_value=mock_store), \
             patch.object(mod, "TradingLogic") as mock_logic, \
             patch.object(mod, "SentimentTrader") as mock_trader, \
             patch.object(mod, "create_shutdown_event") as mock_shutdown:
            mock_logic.from_settings.return_value = MagicMock()
            mock_trader.return_value = AsyncMock()
            evt = asyncio.Event()
            evt.set()
            mock_shutdown.return_value = evt

            await mod.main()

            mock_bus.start.assert_called_once()
            mock_bus.stop.assert_called_once()
            mock_hb.create_background.assert_called_once()
            mock_logic.from_settings.assert_called_once()
            mock_trader.return_value.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_order_tracker_runner_wiring(self):
        import src.live.runners.run_order_tracker as mod

        mock_bus = AsyncMock()
        mock_broker = MagicMock()

        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat") as mock_hb, \
             patch("src.common.startup.banner"), \
             patch.object(mod, "build_broker", return_value=mock_broker), \
             patch.object(mod, "OrderTracker") as mock_tracker, \
             patch.object(mod, "create_shutdown_event") as mock_shutdown:
            mock_tracker.return_value.run = AsyncMock()
            evt = asyncio.Event()
            evt.set()
            mock_shutdown.return_value = evt

            await mod.main()

            mock_bus.start.assert_called_once()
            mock_bus.stop.assert_called_once()
            mock_hb.create_background.assert_called_once()

    @pytest.mark.asyncio
    async def test_watcher_runner_wiring(self):
        import src.live.runners.run_watcher as mod

        mock_bus = AsyncMock()

        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat") as mock_hb, \
             patch("src.common.startup.banner"), \
             patch.object(mod, "build_news_sources", return_value=([MagicMock()], ["rss"])), \
             patch.object(mod, "NewsWatcher") as mock_wn, \
             patch.object(mod, "create_shutdown_event") as mock_shutdown, \
             patch.object(mod, "settings"):
            mock_wn.return_value.run = AsyncMock()
            evt = asyncio.Event()
            evt.set()
            mock_shutdown.return_value = evt

            await mod.main()

            mock_bus.start.assert_called_once()
            mock_bus.stop.assert_called_once()
            mock_hb.create_background.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitor_runner_wiring(self):
        import src.live.runners.run_monitor as mod

        mock_bus = AsyncMock()
        mock_store = MagicMock()
        mock_settings = MagicMock()
        mock_settings.stop_loss_pct = 0.02
        mock_settings.take_profit_pct = 0.04
        mock_settings.sl_check_interval = 60

        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat") as mock_hb, \
             patch("src.common.startup.banner"), \
             patch.object(mod, "PositionStore", return_value=mock_store), \
             patch.object(mod, "TradingLogic") as mock_logic, \
             patch.object(mod, "PriceMonitor") as mock_mon, \
             patch.object(mod, "create_shutdown_event") as mock_shutdown, \
             patch.object(mod, "settings", mock_settings):
            mock_logic.from_settings.return_value = MagicMock()
            mock_mon.return_value.run = AsyncMock()
            evt = asyncio.Event()
            evt.set()
            mock_shutdown.return_value = evt

            await mod.main()

            mock_bus.start.assert_called_once()
            mock_bus.stop.assert_called_once()
            mock_hb.create_background.assert_called_once()
            mock_logic.from_settings.assert_called_once()
            mock_mon.assert_called_once()

    @pytest.mark.asyncio
    async def test_wealth_runner_wiring(self):
        import src.live.runners.run_wealth as mod

        mock_bus = AsyncMock()
        mock_broker = MagicMock()
        mock_store = MagicMock()

        with patch("src.common.event_bus.RedisStreamBus", return_value=mock_bus), \
             patch("src.common.heartbeat.Heartbeat") as mock_hb, \
             patch("src.common.startup.banner"), \
             patch.object(mod, "build_broker", return_value=mock_broker), \
             patch.object(mod, "PositionStore", return_value=mock_store), \
             patch.object(mod, "WealthTracker") as mock_wealth, \
             patch.object(mod, "create_shutdown_event") as mock_shutdown:
            mock_wealth.return_value.run = AsyncMock()
            evt = asyncio.Event()
            evt.set()
            mock_shutdown.return_value = evt

            await mod.main()

            mock_bus.start.assert_called_once()
            mock_bus.stop.assert_called_once()
            mock_hb.create_background.assert_called_once()
            mock_wealth.assert_called_once()
