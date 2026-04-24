"""Run NewsWatcher as its own process. Publishes to [news] channel."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
from src.data.news import NewsAPISource, FinnhubSource, RSSSource, RedditSource, TwitterSource
from src.live.news_watcher import NewsWatcher


async def main():
    bus = RedisEventBus(host=os.getenv("REDIS_HOST", "192.168.0.38"))
    await bus.start()

    sources = []
    if os.getenv("NEWSAPI_KEY"): sources.append(NewsAPISource())
    if os.getenv("FINNHUB_KEY"): sources.append(FinnhubSource())
    if os.getenv("TWITTER_BEARER_TOKEN"): sources.append(TwitterSource())
    sources.append(RSSSource())
    sources.append(RedditSource())

    watcher = NewsWatcher(bus, sources=sources, interval_sec=120)
    print("NewsWatcher process started")
    await watcher.run()

if __name__ == "__main__":
    asyncio.run(main())
