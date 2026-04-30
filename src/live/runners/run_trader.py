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

from src.common.event_bus import RedisStreamBus
from src.common.startup import banner
from src.common.heartbeat import Heartbeat
from src.common.ping import PingResponder
from src.common.position_store import PositionStore
from src.common.trading_logic import TradingLogic
from src.data.utils.db_helper import get_mongo_client
from src.live.sentiment_trader import SentimentTrader
from src.live.price_monitor import PriceMonitor


async def main():
    banner("SentimentTrader", {
        "Subscribes to": "[sentiment], [fill]",
        "Publishes to": "[trade]",
        "Positions": "MongoDB (read/write)",
        "Trade log": "MongoDB trades collection",
        "Redis": os.getenv("REDIS_HOST", "localhost"),
    })

    bus = RedisStreamBus(group="trader")
    await bus.start()

    store = PositionStore()
    logic = TradingLogic(
        threshold=float(os.getenv("THRESHOLD", "0.4")),
        min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.15")),
        max_allocation=float(os.getenv("MAX_ALLOCATION", "0.2")),
        stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "0.05")),
        take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "0.10")),
    )
    monitor = PriceMonitor(bus, store, logic, interval_sec=0)
    trader = SentimentTrader(bus, logic=logic, position_store=store,
                             trade_log=get_mongo_client()["EonTradingDB"]["trades"],
                             price_monitor=monitor)
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
