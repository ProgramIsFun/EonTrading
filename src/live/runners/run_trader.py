"""Run SentimentTrader as its own process. Subscribes to [sentiment], publishes to [trade]."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
from src.common.position_store import PositionStore
from src.live.sentiment_trader import SentimentTrader


async def main():
    redis_host = os.getenv("REDIS_HOST", "192.168.0.38")
    bus = RedisEventBus(host=redis_host)
    await bus.subscribe("sentiment", lambda _: None)
    await bus.start()

    store = PositionStore(host=redis_host)
    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15, position_store=store)
    await trader.start()
    print("SentimentTrader process started (writing positions to Redis)")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
