"""Run NewsWatcher as its own process. Publishes to [news] channel."""
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
from src.data.news import NewsAPISource, FinnhubSource, RSSSource, RedditSource, TwitterSource
from src.live.news_watcher import NewsWatcher


async def main():
    sources = []
    source_names = ["RSS", "Reddit"]
    if os.getenv("NEWSAPI_KEY"):
        sources.append(NewsAPISource()); source_names.append("NewsAPI")
    if os.getenv("FINNHUB_KEY"):
        sources.append(FinnhubSource()); source_names.append("Finnhub")
    if os.getenv("TWITTER_BEARER_TOKEN"):
        sources.append(TwitterSource()); source_names.append("Twitter")
    sources.append(RSSSource())
    sources.append(RedditSource())

    banner("NewsWatcher", {
        "Publishes to": "[news]",
        "Sources": ", ".join(source_names),
        "Redis": os.getenv("REDIS_HOST", "localhost"),
    })

    bus = RedisStreamBus(group="watcher")
    await bus.start()

    watcher = NewsWatcher(bus, sources=sources, interval_sec=120,
                          persist_news=os.getenv("PERSIST_NEWS") == "1",
                          publish=os.getenv("PUBLISH_PIPELINE", "1") == "1")
    logger.info("🟢 Started. Polling every 120s.")
    asyncio.create_task(Heartbeat("watcher", metadata={"sources": ", ".join(source_names), "mode": "distributed"}).run())
    ping = PingResponder(bus, ["watcher"], metadata={"watcher": {"sources": ", ".join(source_names), "mode": "distributed"}})
    await ping.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    watcher_task = asyncio.create_task(watcher.run())
    await stop_event.wait()
    logger.info("Shutting down...")
    watcher_task.cancel()
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
