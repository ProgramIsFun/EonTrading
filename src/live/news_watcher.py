"""NewsWatcher: polls news sources, publishes raw news to event bus."""
import asyncio
from datetime import datetime
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_NEWS
from src.common.news_poller import NewsPoller


class NewsWatcher:
    """Polls news sources and publishes raw news events. That's it."""

    def __init__(self, bus: EventBus, sources: list = None, interval_sec: int = 120, persist_seen: bool = True):
        self.bus = bus
        self.poller = NewsPoller(sources=sources or [], interval_sec=interval_sec, persist_seen=persist_seen)
        self.last_poll: datetime | None = None
        self.last_poll_count: int = 0

    async def run(self):
        print(f"NewsWatcher started, polling every {self.poller.interval}s")
        while True:
            events = self.poller.poll_once()
            self.last_poll = datetime.utcnow()
            self.last_poll_count = len(events)
            for news in events:
                await self.bus.publish(CHANNEL_NEWS, news.to_dict())
            if not events:
                print(f"  ℹ️ No new articles at {self.last_poll.strftime('%H:%M:%S')}")
            await asyncio.sleep(self.poller.interval)
