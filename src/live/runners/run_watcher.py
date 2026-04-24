"""Run NewsWatcher as its own process. Publishes to [news] channel."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
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

    bus = RedisEventBus(host=os.getenv("REDIS_HOST", "192.168.0.38"))
    await bus.start()

    watcher = NewsWatcher(bus, sources=sources, interval_sec=120)
    print(f"  🟢 Started. Polling every 120s.\n")
    asyncio.ensure_future(Heartbeat("watcher", metadata={"sources": ", ".join(source_names)}).run())
    ping = PingResponder(bus, ["watcher"], metadata={"watcher": {"sources": ", ".join(source_names)}})
    await ping.start()
    await watcher.run()

if __name__ == "__main__":
    asyncio.run(main())
