"""Run PriceMonitor as its own process. Watches positions, triggers SL/TP via [trade]."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

from src.common.event_bus import RedisStreamBus
from src.common.heartbeat import Heartbeat
from src.common.position_store import PositionStore
from src.common.shutdown import create_shutdown_event
from src.common.startup import banner
from src.common.trading_logic import TradingLogic
from src.live.price_monitor import PriceMonitor
from src.settings import settings


async def main():
    sl_str = f"{settings.stop_loss_pct * 100:.0f}%"
    tp_str = f"{settings.take_profit_pct * 100:.0f}%"

    banner("PriceMonitor", {
        "Publishes to": "[trade]",
        "Reads from": "MongoDB positions",
        "SL": sl_str,
        "TP": tp_str,
        "Interval": f"{settings.sl_check_interval}s",
    })

    bus = RedisStreamBus(group="monitor")
    await bus.start()

    store = PositionStore()
    logic = TradingLogic(
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
    )
    monitor = PriceMonitor(bus, store, logic, interval_sec=settings.sl_check_interval)

    Heartbeat.create_background("monitor", metadata={"mode": "distributed"})

    logger.info("🟢 Started. Checking prices every %ds.", settings.sl_check_interval)

    monitor_task = asyncio.create_task(monitor.run())
    await create_shutdown_event().wait()
    logger.info("Shutting down...")
    monitor_task.cancel()
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
