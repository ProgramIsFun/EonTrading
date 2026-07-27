"""Run SentimentTrader as its own process. Subscribes to [sentiment], publishes to [trade]."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging("trader")
logger = logging.getLogger(__name__)

from src.common.factories import build_broker
from src.common.position_store import PositionStore
from src.common.shutdown import create_shutdown_event
from src.common.trading_logic import TradingLogic
from src.live.runners import runner_lifecycle
from src.live.sentiment_trader import SentimentTrader


async def main():
    broker = build_broker()

    async with runner_lifecycle("trader", "SentimentTrader", {
        "Subscribes to": "[sentiment]",
        "Publishes to": "[trade]",
        "Positions": "MongoDB (read-only)",
        "Broker": broker.__class__.__name__,
    }) as bus:
        store = PositionStore()
        logic = TradingLogic.from_settings()
        trader = SentimentTrader(bus, logic=logic, position_store=store, broker=broker)
        await trader.start()
        logger.info("🟢 Started. Waiting for [sentiment] events.")
        await create_shutdown_event().wait()

if __name__ == "__main__":
    asyncio.run(main())
