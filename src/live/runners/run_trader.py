"""Run SentimentTrader as its own process. Subscribes to [sentiment]+[fill], publishes to [trade]."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
from src.common.startup import banner
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

    redis_host = os.getenv("REDIS_HOST", "192.168.0.38")
    bus = RedisEventBus(host=redis_host)
    await bus.subscribe("sentiment", lambda _: None)
    await bus.subscribe("fill", lambda _: None)
    await bus.start()

    store = PositionStore()
    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15, position_store=store,
                             trade_log=get_mongo_client()["EonTradingDB"]["trades"])
    await trader.start()
    print(f"  🟢 Started. Waiting for [sentiment] events.\n")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
