"""News watcher: polls news sources, scores sentiment, publishes events."""
import asyncio
from src.data.news import NewsAPISource
from src.strategies.sentiment import BaseSentimentAnalyzer, KeywordSentimentAnalyzer, LLMSentimentAnalyzer
from src.common.event_bus import EventBus, LocalEventBus
from src.common.events import CHANNEL_NEWS, CHANNEL_SENTIMENT, CHANNEL_TRADE, SentimentEvent, TradeEvent
from datetime import datetime


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
    """Listens to sentiment events and decides trades.

    Uses shared TradingLogic from src/common/trading_logic.py — same logic as backtest.
    """

    def __init__(self, bus: EventBus, logic: 'TradingLogic' = None, max_hold_days: int = 0, **kwargs):
        from src.common.trading_logic import TradingLogic
        self.bus = bus
        self.logic = logic or TradingLogic(**kwargs)
        self.holdings: dict[str, datetime] = {}  # symbol → entry time
        self.max_hold_days = max_hold_days

    async def start(self):
        await self.bus.subscribe(CHANNEL_SENTIMENT, self._on_sentiment)
        if self.max_hold_days > 0:
            asyncio.ensure_future(self._hold_checker())

    async def _hold_checker(self):
        """Background task: close positions that exceed max hold period."""
        while True:
            now = datetime.utcnow()
            for symbol in list(self.holdings.keys()):
                entry_time = self.holdings[symbol]
                held_days = (now - entry_time).total_seconds() / 86400
                if held_days >= self.max_hold_days:
                    trade = TradeEvent(
                        symbol=symbol, action="sell",
                        reason=f"max hold {self.max_hold_days}d reached",
                        timestamp=now.isoformat() + "Z",
                    )
                    print(f"  SELL {symbol} (max hold {self.max_hold_days}d reached)")
                    await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
                    del self.holdings[symbol]
            await asyncio.sleep(3600)  # check every hour

    async def _on_sentiment(self, msg: dict):
        event = SentimentEvent.from_dict(msg)
        if not event.symbols:
            return

        for symbol in event.symbols:
            action = None
            if self.logic.should_sell_on_sentiment(event.sentiment, event.confidence, symbol, self.holdings):
                action = "sell"
                self.holdings.pop(symbol, None)
            elif event.confidence >= self.logic.min_confidence and event.sentiment >= self.logic.threshold and symbol not in self.holdings:
                action = "buy"
                self.holdings[symbol] = datetime.utcnow()

            if action:
                trade = TradeEvent(
                    symbol=symbol, action=action,
                    reason=f"sentiment:{event.sentiment} on {event.headline[:60]}",
                    timestamp=datetime.utcnow().isoformat() + "Z",
                )
                print(f"  {action.upper()} {symbol} (sentiment: {event.sentiment}, headline: {event.headline[:60]})")
                await self.bus.publish(CHANNEL_TRADE, trade.to_dict())


async def main():
    import os
    from src.data.news import NewsAPISource, FinnhubSource, RSSSource, RedditSource
    from src.live.brokers.broker import TradeExecutor, LogBroker, FutuBroker

    bus = LocalEventBus()
    await bus.start()

    # Build sources — each activates if its key is set (RSS/Reddit need no key)
    sources = []
    if os.getenv("NEWSAPI_KEY"):
        sources.append(NewsAPISource())
        print("  ✅ NewsAPI")
    if os.getenv("FINNHUB_KEY"):
        sources.append(FinnhubSource())
        print("  ✅ Finnhub")
    sources.append(RSSSource())
    print("  ✅ RSS feeds (Yahoo Finance, CNBC)")
    sources.append(RedditSource())
    print("  ✅ Reddit (r/wallstreetbets, r/stocks, r/investing)")

    if not sources:
        print("No news sources available.")
        return

    # Pick analyzer: keyword (free) or LLM (needs OPENAI_API_KEY)
    if os.getenv("OPENAI_API_KEY"):
        analyzer = LLMSentimentAnalyzer()
        print("Using LLM sentiment analyzer")
    else:
        analyzer = KeywordSentimentAnalyzer()
        print("Using keyword sentiment analyzer (set OPENAI_API_KEY for LLM)")

    # Pick broker: dry-run (default) or Futu (needs OpenD running)
    if os.getenv("FUTU_LIVE"):
        broker = FutuBroker(simulate=not os.getenv("FUTU_REAL"))
        print(f"Using Futu broker ({'real' if os.getenv('FUTU_REAL') else 'simulate'})")
    else:
        broker = LogBroker()
        print("Using dry-run broker (set FUTU_LIVE=1 for Futu)")

    watcher = NewsWatcher(bus, sources=sources, analyzer=analyzer, interval_sec=120)
    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15)
    executor = TradeExecutor(bus, broker)
    await trader.start()
    await executor.start()

    print("Running news sentiment trader (Ctrl+C to stop)...")
    await watcher.run()


if __name__ == "__main__":
    asyncio.run(main())
