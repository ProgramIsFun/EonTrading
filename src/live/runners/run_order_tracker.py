"""Poll pending orders from MongoDB via OrderTracker. Standalone process for distributed mode."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging("order_tracker")
logger = logging.getLogger(__name__)

from src.common.event_bus import RedisStreamBus
from src.common.factories import build_broker
from src.common.heartbeat import Heartbeat
from src.common.order_tracker import OrderTracker
from src.common.shutdown import create_shutdown_event
from src.common.startup import banner


async def main():
    broker = build_broker()

    banner("OrderTracker", {
        "Broker": broker.__class__.__name__,
        "Poll interval": "2s",
    })

    bus = RedisStreamBus(group="order_tracker")
    await bus.start()

    tracker = OrderTracker(bus, broker)
    run_task = asyncio.create_task(tracker.run())

    logger.info("🟢 Started. Polling pending orders every 2s.")
    Heartbeat.create_background("order_tracker", metadata={"broker": broker.__class__.__name__, "mode": "distributed"})

    await create_shutdown_event().wait()
    logger.info("Shutting down...")
    run_task.cancel()
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
