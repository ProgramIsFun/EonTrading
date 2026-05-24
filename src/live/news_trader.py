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
import asyncio
import logging
import signal
import sys
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


class MongoLogHandler(logging.Handler):
    def __init__(self, level=logging.INFO):
        super().__init__(level)
        self._col = None

    @property
    def col(self):
        if self._col is None:
            from src.data.utils.db_helper import get_mongo_client
            self._col = get_mongo_client()["EonTradingDB"]["logs"]
        return self._col

    def emit(self, record):
        try:
            self.col.insert_one({
                "timestamp": datetime.utcnow(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "func": record.funcName,
                "line": record.lineno,
            })
        except Exception:
            pass


# warm the MongoClient cache so MongoLogHandler.emit() doesn't trigger recursive logging
from src.data.utils.db_helper import get_mongo_client
get_mongo_client()
logging.getLogger().addHandler(MongoLogHandler())


async def main_single():
    """All components in one process via LocalEventBus."""
    from src.common.event_bus import LocalEventBus
    from src.common.heartbeat import Heartbeat
    from src.common.ping import PingResponder
    from src.common.position_store import PositionStore
    from src.common.startup import banner, env_status
    from src.common.trading_logic import TradingLogic
    from src.data.news.loader import build_news_sources
    from src.data.utils.db_helper import get_mongo_client
    from src.live.analyzer_service import AnalyzerService
    from src.live.brokers.broker import AlpacaBroker, FutuBroker, IBKRBroker, PaperBroker, TradeExecutor
    from src.live.news_watcher import NewsWatcher
    from src.live.price_monitor import PriceMonitor
    from src.live.sentiment_trader import SentimentTrader
    from src.settings import settings
    from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer

    # --- Sources ---
    sources, source_names = build_news_sources()

    # --- Analyzer ---
    if settings.openai_api_key or settings.opencode_api_key:
        analyzer = LLMSentimentAnalyzer()
        analyzer_name = f"LLM ({analyzer.model})"
    else:
        analyzer = KeywordSentimentAnalyzer()
        analyzer_name = "Keyword (free)"

    # --- Broker ---
    broker_name = settings.broker.lower()
    if broker_name == "futu":
        broker = FutuBroker(simulate=not settings.futu_real, confirm_mode=settings.futu_confirm)
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

    store = PositionStore()
    logic = TradingLogic(
        threshold=settings.threshold,
        min_confidence=settings.min_confidence,
        max_allocation=settings.max_allocation,
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
    )
    monitor = PriceMonitor(bus, store, logic, interval_sec=60)
    trader = SentimentTrader(bus, logic=logic, position_store=store,
                             trade_log=get_mongo_client()["EonTradingDB"]["trades"],
                             broker=broker, price_monitor=monitor)
    analyzer_svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    watcher = NewsWatcher(bus, sources=sources, interval_sec=120,
                          persist_news=settings.persist_news,
                          publish=settings.publish_pipeline)
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
