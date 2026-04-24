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
    from src.common.startup import banner, env_status
    from src.data.news import NewsAPISource, FinnhubSource, RSSSource, RedditSource, TwitterSource
    from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer
    from src.live.news_watcher import NewsWatcher
    from src.live.analyzer_service import AnalyzerService
    from src.live.sentiment_trader import SentimentTrader
    from src.live.brokers.broker import TradeExecutor, LogBroker, FutuBroker, IBKRBroker, AlpacaBroker
    from src.common.position_store import PositionStore
    from src.data.utils.db_helper import get_mongo_client
    from src.common.heartbeat import Heartbeat

    # --- Sources ---
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

    # --- Analyzer ---
    if os.getenv("OPENAI_API_KEY"):
        analyzer = LLMSentimentAnalyzer()
        analyzer_name = f"LLM ({analyzer.model})"
    else:
        analyzer = KeywordSentimentAnalyzer()
        analyzer_name = "Keyword (free)"

    # --- Broker ---
    broker_name = os.getenv("BROKER", "log").lower()
    if broker_name == "futu":
        broker = FutuBroker(simulate=not os.getenv("FUTU_REAL"))
    elif broker_name == "ibkr":
        broker = IBKRBroker()
    elif broker_name == "alpaca":
        broker = AlpacaBroker()
    else:
        broker = LogBroker()

    # --- Startup banner ---
    banner("EonTrading — Single Process Mode", {
        "Bus": "LocalEventBus (in-memory)",
        "Sources": ", ".join(source_names),
        "Analyzer": analyzer_name,
        "Broker": broker.__class__.__name__,
    })
    env_status()

    # --- Wire up ---
    bus = LocalEventBus()
    await bus.start()

    store = PositionStore()
    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15, position_store=store,
                             trade_log=get_mongo_client()["EonTradingDB"]["trades"])
    analyzer_svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    watcher = NewsWatcher(bus, sources=sources, interval_sec=120)
    executor = TradeExecutor(bus, broker)

    await analyzer_svc.start()
    await trader.start()
    await executor.start()

    for name in ["watcher", "analyzer", "trader", "executor"]:
        asyncio.ensure_future(Heartbeat(name, metadata={"mode": "single"}).run())

    print(f"\n  🟢 All components started. Polling every 120s.\n")
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
