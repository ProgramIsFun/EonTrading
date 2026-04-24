"""Run SentimentTrader as its own process. Subscribes to [sentiment]+[fill], publishes to [trade]."""
import asyncio, logging, os, signal
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from src.common.event_bus import RedisEventBus
from src.common.startup import banner
from src.common.heartbeat import Heartbeat
from src.common.ping import PingResponder
from src.common.position_store import PositionStore
from src.data.utils.db_helper import get_mongo_client
from src.live.sentiment_trader import SentimentTrader


async def main():
    banner("SentimentTrader", {
        "Subscribes to": "[sentiment], [fill]",
        "Publishes to": "[trade]",
        "Positions": "MongoDB (read/write)",
        "Trade log": "MongoDB trades collection",
        "Redis": os.getenv("REDIS_HOST", "localhost"),
    })

    bus = RedisEventBus(group="trader")
    await bus.start()

    store = PositionStore()
    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15, position_store=store,
                             trade_log=get_mongo_client()["EonTradingDB"]["trades"])
    await trader.start()
    logger.info("🟢 Started. Waiting for [sentiment] events.")
    asyncio.create_task(Heartbeat("trader", metadata={"mode": "distributed"}).run())
    ping = PingResponder(bus, ["trader"], metadata={"trader": {"mode": "distributed"}})
    await ping.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()
    logger.info("Shutting down...")
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
