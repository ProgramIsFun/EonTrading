"""NewsWatcher: polls news sources, analyzes sentiment, publishes to event bus."""
import asyncio
from src.strategies.sentiment import BaseSentimentAnalyzer, KeywordSentimentAnalyzer
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_NEWS, CHANNEL_SENTIMENT
from src.common.news_poller import NewsPoller


class NewsWatcher:
    """Polls news, analyzes sentiment, publishes to event bus."""

    def __init__(self, bus: EventBus, sources: list = None, analyzer: BaseSentimentAnalyzer = None, interval_sec: int = 120, get_positions=None):
        self.bus = bus
        self.poller = NewsPoller(sources=sources or [], interval_sec=interval_sec)
        self.analyzer = analyzer or KeywordSentimentAnalyzer()
        self.get_positions = get_positions  # callable that returns current holdings dict

    async def run(self):
        print(f"NewsWatcher started, polling every {self.poller.interval}s")
        while True:
            positions = self.get_positions() if self.get_positions else None
            for news in self.poller.poll_once():
                await self.bus.publish(CHANNEL_NEWS, news.to_dict())
                sentiment = self.analyzer.analyze(news, positions=positions)
                if sentiment.confidence > 0:
                    await self.bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
                    print(f"  [{sentiment.sentiment:+.2f}] {sentiment.headline[:80]}")
            await asyncio.sleep(self.poller.interval)
