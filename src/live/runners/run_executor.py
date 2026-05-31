"""Run TradeExecutor as its own process. Subscribes to [trade], writes to orders collection."""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from src.common.log_handler import maybe_enable_mongo_logging
maybe_enable_mongo_logging()

from src.common.event_bus import RedisStreamBus
from src.common.factories import build_broker
from src.common.heartbeat import Heartbeat
from src.common.shutdown import create_shutdown_event
from src.common.startup import banner
from src.live.brokers.broker import TradeExecutor


async def main():
    broker = build_broker()

    banner("TradeExecutor", {
        "Subscribes to": "[trade]",
        "Publishes to": "orders (OrderTracker polls)",
        "Broker": broker.__class__.__name__,
    })

    bus = RedisStreamBus(group="executor")
    await bus.start()

    executor = TradeExecutor(bus, broker)
    await executor.start()
    logger.info("🟢 Started. Waiting for [trade] events.")
    Heartbeat.create_background("executor", metadata={"broker": broker.__class__.__name__, "mode": "distributed"})

    await create_shutdown_event().wait()
    logger.info("Shutting down...")
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
