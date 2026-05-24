"""Run SentimentTrader as its own process. Subscribes to [sentiment]+[fill], publishes to [trade]."""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from src.common.event_bus import RedisStreamBus
from src.common.heartbeat import Heartbeat
from src.common.ping import PingResponder
from src.common.position_store import PositionStore
from src.common.shutdown import create_shutdown_event
from src.common.startup import banner
from src.common.trading_logic import TradingLogic
from src.data.utils.db_helper import get_mongo_client
from src.live.price_monitor import PriceMonitor
from src.live.sentiment_trader import SentimentTrader
from src.settings import settings


async def main():
    banner("SentimentTrader", {
        "Subscribes to": "[sentiment], [fill]",
        "Publishes to": "[trade]",
        "Positions": "MongoDB (read/write)",
        "Trade log": "MongoDB trades collection",
    })

    bus = RedisStreamBus(group="trader")
    await bus.start()

    store = PositionStore()
    logic = TradingLogic(
        threshold=settings.threshold,
        min_confidence=settings.min_confidence,
        max_allocation=settings.max_allocation,
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
    )
    monitor = PriceMonitor(bus, store, logic, interval_sec=0)
    trader = SentimentTrader(bus, logic=logic, position_store=store,
                             trade_log=get_mongo_client()["EonTradingDB"]["trades"],
                             price_monitor=monitor)
    await trader.start()
    logger.info("🟢 Started. Waiting for [sentiment] events.")
    Heartbeat.create_background("trader", metadata={"mode": "distributed"})
    await PingResponder.create_and_start(bus, ["trader"], metadata={"trader": {"mode": "distributed"}})

    await create_shutdown_event().wait()
    logger.info("Shutting down...")
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
