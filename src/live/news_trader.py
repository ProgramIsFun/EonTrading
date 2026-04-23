"""Entry point: wires all live trading components together."""
import asyncio
from src.common.event_bus import LocalEventBus
from src.live.news_watcher import NewsWatcher
from src.live.sentiment_trader import SentimentTrader
from src.live.brokers.broker import TradeExecutor, LogBroker, FutuBroker
from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer


async def main():
    import os
    from src.data.news import NewsAPISource, FinnhubSource, RSSSource, RedditSource

    bus = LocalEventBus()
    await bus.start()

    # Build sources
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

    # Pick analyzer
    if os.getenv("OPENAI_API_KEY"):
        analyzer = LLMSentimentAnalyzer()
        print("Using LLM sentiment analyzer")
    else:
        analyzer = KeywordSentimentAnalyzer()
        print("Using keyword sentiment analyzer (set OPENAI_API_KEY for LLM)")

    # Pick broker
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
