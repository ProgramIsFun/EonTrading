"""Run AnalyzerService as its own process. Subscribes to [news], publishes to [sentiment]."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer
from src.live.analyzer_service import AnalyzerService


async def main():
    bus = RedisEventBus(host=os.getenv("REDIS_HOST", "192.168.0.38"))
    await bus.subscribe("news", lambda _: None)  # register before start
    await bus.start()

    analyzer = LLMSentimentAnalyzer() if os.getenv("OPENAI_API_KEY") else KeywordSentimentAnalyzer()

    # In distributed mode, query positions from broker or DB
    # For now, no position context (can be added via shared DB later)
    svc = AnalyzerService(bus, analyzer=analyzer)
    await svc.start()
    print("AnalyzerService process started")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
