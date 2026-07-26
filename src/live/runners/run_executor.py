"""Run TradeExecutor as its own process. Subscribes to [trade], writes to orders collection."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging("executor")
logger = logging.getLogger(__name__)

from src.common.factories import build_broker
from src.common.shutdown import create_shutdown_event
from src.live.brokers import TradeExecutor
from src.live.order_logger import mongo_log_order
from src.live.runners import runner_lifecycle


async def main():
    broker = build_broker()

    async with runner_lifecycle("executor", "TradeExecutor", {
        "Subscribes to": "[trade]",
        "Publishes to": "orders (OrderTracker polls)",
        "Broker": broker.__class__.__name__,
    }) as bus:
        executor = TradeExecutor(bus, broker, log_order=mongo_log_order)
        await executor.start()
        logger.info("🟢 Started. Waiting for [trade] events.")
        await create_shutdown_event().wait()

if __name__ == "__main__":
    asyncio.run(main())
