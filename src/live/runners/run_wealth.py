"""Run WealthTracker as its own process. Logs portfolio wealth every 60s."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging("wealth")
logger = logging.getLogger(__name__)

from src.common.factories import build_broker
from src.common.position_store import PositionStore
from src.common.shutdown import create_shutdown_event
from src.live.runners import runner_lifecycle
from src.live.wealth_tracker import WealthTracker


async def main():
    broker = build_broker()

    async with runner_lifecycle("wealth", "WealthTracker", {
        "Reads from": "Broker + MongoDB positions",
        "Writes to": "logs/wealth.log + MongoDB wealth_history",
        "Broker": broker.__class__.__name__,
        "Interval": "60s",
    }) as bus:
        store = PositionStore()
        wealth = WealthTracker(broker, position_store=store, interval_sec=60)
        logger.info("🟢 Started. Logging wealth every 60s.")
        wealth_task = asyncio.create_task(wealth.run())
        await create_shutdown_event().wait()
        wealth_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
