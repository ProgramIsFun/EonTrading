"""Poll pending orders from MongoDB via OrderTracker. Standalone process for distributed mode."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging("order_tracker")
logger = logging.getLogger(__name__)

from src.common.factories import build_broker
from src.common.order_tracker import OrderTracker
from src.common.shutdown import create_shutdown_event
from src.live.runners import runner_lifecycle


async def main():
    broker = build_broker()

    async with runner_lifecycle("order_tracker", "OrderTracker", {
        "Broker": broker.__class__.__name__,
        "Poll interval": "2s",
    }) as bus:
        tracker = OrderTracker(bus, broker)
        run_task = asyncio.create_task(tracker.run())
        logger.info("🟢 Started. Polling pending orders every 2s.")
        await create_shutdown_event().wait()
        run_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
