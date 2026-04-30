"""Entry point for live trading.

Two modes:
  python3 -m src.live.news_trader              # single process (LocalEventBus)
  python3 -m src.live.news_trader --distributed # separate processes (RedisStreamBus)

For distributed mode, run each runner in its own terminal:
  python3 -m src.live.runners.run_watcher
  python3 -m src.live.runners.run_analyzer
  python3 -m src.live.runners.run_trader
  python3 -m src.live.runners.run_executor
"""
import asyncio, logging, os, signal, sys
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main_single():
    """All components in one process via LocalEventBus."""
    from src.common.event_bus import LocalEventBus
    from src.common.startup import banner, env_status
    from src.data.news import NewsAPISource, FinnhubSource, RSSSource, RedditSource, TwitterSource
    from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer
    from src.live.news_watcher import NewsWatcher
    from src.live.analyzer_service import AnalyzerService
    from src.live.sentiment_trader import SentimentTrader
    from src.live.brokers.broker import TradeExecutor, PaperBroker, FutuBroker, IBKRBroker, AlpacaBroker
    from src.common.position_store import PositionStore
    from src.common.trading_logic import TradingLogic
    from src.data.utils.db_helper import get_mongo_client
    from src.common.heartbeat import Heartbeat
    from src.common.ping import PingResponder

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
        confirm = os.getenv("FUTU_CONFIRM", "poll")  # poll or callback
        broker = FutuBroker(simulate=not os.getenv("FUTU_REAL"), confirm_mode=confirm)
    elif broker_name == "ibkr":
        broker = IBKRBroker()
    elif broker_name == "alpaca":
        broker = AlpacaBroker()
    else:
        broker = PaperBroker()

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

    from src.live.price_monitor import PriceMonitor

    store = PositionStore()
    logic = TradingLogic(
        threshold=float(os.getenv("THRESHOLD", "0.4")),
        min_confidence=float(os.getenv("MIN_CONFIDENCE", "0.15")),
        max_allocation=float(os.getenv("MAX_ALLOCATION", "0.2")),
        stop_loss_pct=float(os.getenv("STOP_LOSS_PCT", "0.05")),
        take_profit_pct=float(os.getenv("TAKE_PROFIT_PCT", "0.10")),
    )
    monitor = PriceMonitor(bus, store, logic, interval_sec=60)
    trader = SentimentTrader(bus, logic=logic, position_store=store,
                             trade_log=get_mongo_client()["EonTradingDB"]["trades"],
                             broker=broker, price_monitor=monitor)
    analyzer_svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    watcher = NewsWatcher(bus, sources=sources, interval_sec=120,
                          persist_news=bool(os.getenv("PERSIST_NEWS")),
                          publish=bool(os.getenv("PUBLISH_PIPELINE", "1")))
    executor = TradeExecutor(bus, broker)

    await analyzer_svc.start()
    await trader.start()
    await executor.start()
    monitor_task = asyncio.create_task(monitor.run(broker))

    for name in ["watcher", "analyzer", "trader", "executor", "monitor"]:
        asyncio.create_task(Heartbeat(name, metadata={"mode": "single"}).run())

    ping = PingResponder(bus, ["watcher", "analyzer", "trader", "executor"], metadata={
        "watcher": {"sources": ", ".join(source_names), "mode": "single"},
        "analyzer": {"analyzer": analyzer_name, "mode": "single"},
        "trader": {"mode": "single"},
        "executor": {"broker": broker.__class__.__name__, "mode": "single"},
    })
    await ping.start()

    logger.info("🟢 All components started. Polling every 120s.")

    # Reconcile on startup
    from src.common.reconcile import reconcile
    await reconcile(broker, store)

    # Graceful shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    watcher_task = asyncio.create_task(watcher.run())

    await stop_event.wait()
    logger.info("Shutting down...")
    watcher_task.cancel()
    monitor_task.cancel()
    await bus.stop()
    logger.info("Shutdown complete.")


if __name__ == "__main__":
    if "--distributed" in sys.argv:
        print("Distributed mode — run each runner separately:")
        print("  python3 -m src.live.runners.run_watcher")
        print("  python3 -m src.live.runners.run_analyzer")
        print("  python3 -m src.live.runners.run_trader")
        print("  python3 -m src.live.runners.run_executor")
    else:
        asyncio.run(main_single())
