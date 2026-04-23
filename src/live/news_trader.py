"""Entry point for live trading.

Two modes:
  python3 -m src.live.news_trader              # single process (LocalEventBus)
  python3 -m src.live.news_trader --distributed # separate processes (RedisEventBus)

For distributed mode, run each runner in its own terminal:
  python3 -m src.live.runners.run_watcher
  python3 -m src.live.runners.run_trader
  python3 -m src.live.runners.run_executor
"""
import asyncio, os, sys
from dotenv import load_dotenv
load_dotenv()


async def main_single():
    """All components in one process via LocalEventBus."""
    from src.common.event_bus import LocalEventBus
    from src.data.news import NewsAPISource, FinnhubSource, RSSSource, RedditSource
    from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer
    from src.live.news_watcher import NewsWatcher
    from src.live.sentiment_trader import SentimentTrader
    from src.live.brokers.broker import TradeExecutor, LogBroker, FutuBroker

    bus = LocalEventBus()
    await bus.start()

    sources = []
    if os.getenv("NEWSAPI_KEY"): sources.append(NewsAPISource())
    if os.getenv("FINNHUB_KEY"): sources.append(FinnhubSource())
    sources.append(RSSSource())
    sources.append(RedditSource())

    analyzer = LLMSentimentAnalyzer() if os.getenv("OPENAI_API_KEY") else KeywordSentimentAnalyzer()
    broker = FutuBroker(simulate=not os.getenv("FUTU_REAL")) if os.getenv("FUTU_LIVE") else LogBroker()

    watcher = NewsWatcher(bus, sources=sources, analyzer=analyzer, interval_sec=120)
    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15)
    executor = TradeExecutor(bus, broker)
    await trader.start()
    await executor.start()

    print("Running single-process mode (LocalEventBus)...")
    await watcher.run()


if __name__ == "__main__":
    if "--distributed" in sys.argv:
        print("Distributed mode — run each runner separately:")
        print("  python3 -m src.live.runners.run_watcher")
        print("  python3 -m src.live.runners.run_trader")
        print("  python3 -m src.live.runners.run_executor")
    else:
        asyncio.run(main_single())
