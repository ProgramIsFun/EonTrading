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
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from src.common.log_handler import maybe_enable_mongo_logging
maybe_enable_mongo_logging()


async def main_single():
    """All components in one process via LocalEventBus."""
    from src.common.event_bus import LocalEventBus
    from src.common.factories import build_analyzer, build_broker
    from src.common.heartbeat import Heartbeat
    from src.common.position_store import PositionStore
    from src.common.shutdown import create_shutdown_event
    from src.common.startup import banner, env_status
    from src.common.trading_logic import TradingLogic
    from src.data.news.loader import build_news_sources
    from src.data.utils.db_helper import get_mongo_client
    from src.live.analyzer_service import AnalyzerService
    from src.live.brokers.broker import TradeExecutor
    from src.live.news_watcher import NewsWatcher
    from src.live.price_monitor import PriceMonitor
    from src.live.sentiment_trader import SentimentTrader
    from src.settings import settings

    # --- Sources ---
    sources, source_names = build_news_sources()

    # --- Analyzer ---
    analyzer, analyzer_name = build_analyzer()

    # --- Broker ---
    broker = build_broker()

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
                             broker=broker, price_monitor=monitor)
    analyzer_svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    watcher = NewsWatcher(bus, sources=sources, interval_sec=120,
                          persist_news=settings.persist_news,
                          publish=settings.publish_pipeline)
    executor = TradeExecutor(bus, broker,
                             position_store=store,
                             trade_log=get_mongo_client()["EonTradingDB"]["trades"],
                             price_monitor=monitor)

    await analyzer_svc.start()
    await trader.start()
    await executor.start()
    monitor_task = asyncio.create_task(monitor.run(broker))

    for name in ["watcher", "analyzer", "trader", "executor", "monitor"]:
        Heartbeat.create_background(name, metadata={"mode": "single"})

    logger.info("🟢 All components started. Polling every 120s.")

    # Reconcile on startup
    from src.common.reconcile import reconcile
    await reconcile(broker, store)

    # Graceful shutdown
    watcher_task = asyncio.create_task(watcher.run())

    await create_shutdown_event().wait()
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
