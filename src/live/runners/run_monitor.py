"""Run PriceMonitor as its own process. Watches positions, triggers SL/TP via [trade]."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging("monitor")
logger = logging.getLogger(__name__)

from src.common.position_store import PositionStore
from src.common.shutdown import create_shutdown_event
from src.common.trading_logic import TradingLogic
from src.live.price_monitor import PriceMonitor
from src.live.runners import runner_lifecycle
from src.settings import settings


async def main():
    sl_str = f"{settings.stop_loss_pct * 100:.0f}%"
    tp_str = f"{settings.take_profit_pct * 100:.0f}%"

    async with runner_lifecycle("monitor", "PriceMonitor", {
        "Publishes to": "[trade]",
        "Reads from": "MongoDB positions",
        "SL": sl_str,
        "TP": tp_str,
        "Interval": f"{settings.sl_check_interval}s",
    }) as bus:
        store = PositionStore()
        logic = TradingLogic.from_settings()
        monitor = PriceMonitor(bus, store, logic, interval_sec=settings.sl_check_interval)
        logger.info("🟢 Started. Checking prices every %ds.", settings.sl_check_interval)
        monitor_task = asyncio.create_task(monitor.run())
        await create_shutdown_event().wait()
        monitor_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
