"""News watcher: polls news sources, scores sentiment, publishes events."""
import asyncio
from src.data.news import NewsAPISource
from src.strategies.sentiment import BaseSentimentAnalyzer, KeywordSentimentAnalyzer, LLMSentimentAnalyzer
from src.common.event_bus import EventBus, LocalEventBus
from src.common.events import CHANNEL_NEWS, CHANNEL_SENTIMENT, CHANNEL_TRADE, SentimentEvent


class NewsWatcher:
    """Polls news, analyzes sentiment, publishes to event bus."""

    def __init__(self, bus: EventBus, sources: list = None, analyzer: BaseSentimentAnalyzer = None, interval_sec: int = 120):
        self.bus = bus
        self.sources = sources or []
        self.analyzer = analyzer or KeywordSentimentAnalyzer()
        self.interval = interval_sec

    async def run(self):
        print(f"NewsWatcher started, polling every {self.interval}s")
        while True:
            for source in self.sources:
                events = source.fetch_latest()
                for news in events:
                    await self.bus.publish(CHANNEL_NEWS, news.to_dict())
                    sentiment = self.analyzer.analyze(news)
                    if sentiment.confidence > 0:
                        await self.bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
                        print(f"  [{sentiment.sentiment:+.2f}] {sentiment.headline[:80]}")
            await asyncio.sleep(self.interval)


class SentimentTrader:
    """Listens to sentiment events and decides trades."""

    def __init__(self, bus: EventBus, threshold: float = 0.5, min_confidence: float = 0.4):
        self.bus = bus
        self.threshold = threshold
        self.min_confidence = min_confidence
        self.holdings = set()  # symbols we're holding

    async def start(self):
        await self.bus.subscribe(CHANNEL_SENTIMENT, self._on_sentiment)

    async def _on_sentiment(self, msg: dict):
        event = SentimentEvent.from_dict(msg)
        if event.confidence < self.min_confidence:
            return
        if not event.symbols:
            return

        for symbol in event.symbols:
            if event.sentiment <= -self.threshold and symbol in self.holdings:
                print(f"  SELL {symbol} (sentiment: {event.sentiment}, headline: {event.headline[:60]})")
                self.holdings.discard(symbol)
                # TODO: publish TradeEvent and execute via broker

            elif event.sentiment >= self.threshold and symbol not in self.holdings:
                print(f"  BUY {symbol} (sentiment: {event.sentiment}, headline: {event.headline[:60]})")
                self.holdings.add(symbol)
                # TODO: publish TradeEvent and execute via broker


async def main():
    import os
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        print("Set NEWSAPI_KEY env var. Get one free at https://newsapi.org")
        return

    bus = LocalEventBus()
    await bus.start()

    source = NewsAPISource(api_key=api_key)

    # Pick analyzer: keyword (free) or LLM (needs OPENAI_API_KEY)
    if os.getenv("OPENAI_API_KEY"):
        analyzer = LLMSentimentAnalyzer()
        print("Using LLM sentiment analyzer")
    else:
        analyzer = KeywordSentimentAnalyzer()
        print("Using keyword sentiment analyzer (set OPENAI_API_KEY for LLM)")

    watcher = NewsWatcher(bus, sources=[source], analyzer=analyzer, interval_sec=120)
    trader = SentimentTrader(bus, threshold=0.5, min_confidence=0.4)
    await trader.start()

    print("Running news sentiment trader (Ctrl+C to stop)...")
    await watcher.run()


if __name__ == "__main__":
    asyncio.run(main())
