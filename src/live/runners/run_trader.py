"""Run SentimentTrader as its own process. Subscribes to [sentiment], publishes to [trade]."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
from src.live.sentiment_trader import SentimentTrader


async def main():
    bus = RedisEventBus(host=os.getenv("REDIS_HOST", "192.168.0.38"))
    await bus.subscribe("sentiment", lambda _: None)  # register before start
    await bus.start()

    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15)
    await trader.start()
    print("SentimentTrader process started")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
