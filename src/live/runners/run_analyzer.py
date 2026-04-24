"""Run AnalyzerService as its own process. Subscribes to [news], publishes to [sentiment]."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
from src.common.startup import banner
from src.common.position_store import PositionStore
from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer
from src.live.analyzer_service import AnalyzerService


async def main():
    if os.getenv("OPENAI_API_KEY"):
        analyzer = LLMSentimentAnalyzer()
        analyzer_name = f"LLM ({analyzer.model})"
    else:
        analyzer = KeywordSentimentAnalyzer()
        analyzer_name = "Keyword (free)"

    banner("AnalyzerService", {
        "Subscribes to": "[news]",
        "Publishes to": "[sentiment]",
        "Analyzer": analyzer_name,
        "Positions from": "MongoDB",
        "Redis": os.getenv("REDIS_HOST", "localhost"),
    })

    redis_host = os.getenv("REDIS_HOST", "192.168.0.38")
    bus = RedisEventBus(host=redis_host)
    await bus.subscribe("news", lambda _: None)
    await bus.start()

    store = PositionStore()
    svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    await svc.start()
    print(f"  🟢 Started. Waiting for [news] events.\n")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
