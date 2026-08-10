"""Shared live pipeline assembly — builds the standard component graph once.

Use this from live mode, replay mode, and the API backtest path so the
trader/analyzer/monitor wiring stays identical everywhere.  The trader owns
execution and order logging, so there is no separate executor component.
"""
import logging
from dataclasses import dataclass

from src.common.event_bus import EventBus
from src.common.position_store import BasePositionStore
from src.common.trading_logic import TradingLogic
from src.live.analyzer_service import AnalyzerService
from src.live.brokers import Broker
from src.live.price_monitor import PriceMonitor
from src.live.sentiment_trader import SentimentTrader
from src.strategies.sentiment import BaseSentimentAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class Pipeline:
    trader: SentimentTrader
    analyzer_svc: AnalyzerService
    monitor: PriceMonitor


async def build_pipeline(
    bus: EventBus,
    *,
    broker: Broker,
    analyzer: BaseSentimentAnalyzer,
    position_store: BasePositionStore,
    logic: TradingLogic,
    monitor_interval_sec: int = 60,
    log_order=None,
) -> Pipeline:
    """Assemble and start the standard live component graph.

    Builds the PriceMonitor, SentimentTrader, and AnalyzerService wired to
    the shared event bus, then starts the trader/analyzer services so they
    begin consuming messages.  The trader executes trades via *broker* and
    logs orders through *log_order* (for OrderTracker confirmation).
    """
    monitor = PriceMonitor(bus, position_store, logic, interval_sec=monitor_interval_sec,
                           broker=broker, log_order=log_order)
    trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=position_store,
                             log_order=log_order)
    analyzer_svc = AnalyzerService(bus, analyzer=analyzer, get_positions=position_store.get_positions)

    await analyzer_svc.start()
    await trader.start()

    return Pipeline(trader=trader, analyzer_svc=analyzer_svc, monitor=monitor)
