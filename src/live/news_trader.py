"""Entry point for live trading.

Two modes:
  python3 -m src.live.news_trader              # single process (LocalEventBus)
  python3 -m src.live.news_trader --distributed # separate processes (RedisEventBus)

For distributed mode, run each runner in its own terminal:
  python3 -m src.live.runners.run_watcher
  python3 -m src.live.runners.run_analyzer
  python3 -m src.live.runners.run_trader
  python3 -m src.live.runners.run_executor
"""
import asyncio, os, sys
from dotenv import load_dotenv
load_dotenv()


async def main_single():
    """All components in one process via LocalEventBus."""
    from src.common.event_bus import LocalEventBus
    from src.data.news import NewsAPISource, FinnhubSource, RSSSource, RedditSource, TwitterSource
    from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer
    from src.live.news_watcher import NewsWatcher
    from src.live.analyzer_service import AnalyzerService
    from src.live.sentiment_trader import SentimentTrader
    from src.live.brokers.broker import TradeExecutor, LogBroker, FutuBroker, IBKRBroker, AlpacaBroker
    from src.common.position_store import PositionStore
    from src.data.utils.db_helper import get_mongo_client

    bus = LocalEventBus()
    await bus.start()

    sources = []
    if os.getenv("NEWSAPI_KEY"): sources.append(NewsAPISource())
    if os.getenv("FINNHUB_KEY"): sources.append(FinnhubSource())
    if os.getenv("TWITTER_BEARER_TOKEN"): sources.append(TwitterSource())
    sources.append(RSSSource())
    sources.append(RedditSource())

    analyzer = LLMSentimentAnalyzer() if os.getenv("OPENAI_API_KEY") else KeywordSentimentAnalyzer()

    # Broker selection via BROKER env var: futu, ibkr, alpaca, log (default)
    broker_name = os.getenv("BROKER", "log").lower()
    if broker_name == "futu":
        broker = FutuBroker(simulate=not os.getenv("FUTU_REAL"))
    elif broker_name == "ibkr":
        broker = IBKRBroker()
    elif broker_name == "alpaca":
        broker = AlpacaBroker()
    else:
        broker = LogBroker()
    store = PositionStore()

    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15, position_store=store,
                             trade_log=get_mongo_client()["EonTradingDB"]["trades"])
    analyzer_svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    watcher = NewsWatcher(bus, sources=sources, interval_sec=120)
    executor = TradeExecutor(bus, broker)

    await analyzer_svc.start()
    await trader.start()
    await executor.start()

    print("Running single-process mode (LocalEventBus)...")
    await watcher.run()


if __name__ == "__main__":
    if "--distributed" in sys.argv:
        print("Distributed mode — run each runner separately:")
        print("  python3 -m src.live.runners.run_watcher")
        print("  python3 -m src.live.runners.run_analyzer")
        print("  python3 -m src.live.runners.run_trader")
        print("  python3 -m src.live.runners.run_executor")
    else:
        asyncio.run(main_single())
