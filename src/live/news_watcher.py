"""NewsWatcher: polls news sources, publishes raw news to event bus."""
import asyncio
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_NEWS
from src.common.news_poller import NewsPoller


class NewsWatcher:
    """Polls news sources and publishes raw news events. That's it."""

    def __init__(self, bus: EventBus, sources: list = None, interval_sec: int = 120):
        self.bus = bus
        self.poller = NewsPoller(sources=sources or [], interval_sec=interval_sec)

    async def run(self):
        print(f"NewsWatcher started, polling every {self.poller.interval}s")
        while True:
            for news in self.poller.poll_once():
                await self.bus.publish(CHANNEL_NEWS, news.to_dict())
            await asyncio.sleep(self.poller.interval)
