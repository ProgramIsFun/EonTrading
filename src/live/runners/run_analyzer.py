"""Run AnalyzerService as its own process. Subscribes to [news], publishes to [sentiment]."""
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

    bus = RedisEventBus()
    await bus.subscribe("news", lambda _: None)
    await bus.start()

    store = PositionStore()
    svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    await svc.start()
    logger.info("🟢 Started. Waiting for [news] events.")
    asyncio.create_task(Heartbeat("analyzer", metadata={"analyzer": analyzer_name, "mode": "distributed"}).run())
    ping = PingResponder(bus, ["analyzer"], metadata={"analyzer": {"analyzer": analyzer_name, "mode": "distributed"}})
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
