"""TradeExecutor — routes [trade] events to the configured broker."""
import logging

from src.common.events import CHANNEL_TRADE, TradeEvent
from src.common.event_bus import EventBus
from src.common.log_handler import ComponentFilter

from .broker import Broker

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("executor"))


class TradeExecutor:
    """Listens to trade events, submits orders via broker, logs via injected callable.

    Does NOT track fill results — OrderTracker handles confirmation via polling.

    Parameters
    ----------
    bus : EventBus
    broker : Broker
    log_order : async callable (trade, order_id, broker_name) -> None
        Called after each successful order submission.  Pass ``noop_log_order``
        (or omit) to disable audit logging.  Default implementation is a no-op.
    log_failed_order : async callable (trade, broker_name, error) -> None
        Called when broker rejects the order.  Logs to MongoDB for audit trail.
    """

    def __init__(self, bus: EventBus, broker: Broker, log_order=None, log_failed_order=None):
        from src.live.order_logger import noop_log_order
        self.bus = bus
        self.broker = broker
        self._log_order = log_order or noop_log_order
        self._log_failed_order = log_failed_order
        self._seen: set[str] = set()

    async def start(self):
        await self.bus.subscribe(CHANNEL_TRADE, self._on_trade)

    async def _on_trade(self, msg: dict):
        trade = TradeEvent.from_dict(msg)
        dedup_key = f"{trade.symbol}:{trade.action}:{trade.timestamp}"
        if dedup_key in self._seen:
            logger.warning("Duplicate trade ignored: %s %s @ %s", trade.action, trade.symbol, trade.timestamp)
            return
        self._seen.add(dedup_key)
        if len(self._seen) > 10000:
            self._seen = set(list(self._seen)[-5000:])

        order_id = await self.broker.execute(trade)
        if order_id is None:
            logger.error("Order submission failed: %s %s", trade.action.upper(), trade.symbol)
            if self._log_failed_order:
                await self._log_failed_order(trade, self.broker.__class__.__name__, "broker returned None")
            return
        await self._log_order(trade, order_id, self.broker.__class__.__name__)
        logger.info("✅ %s %s qty=%d @ $%.2f (order_id=%s, broker=%s)",
                     trade.action.upper(), trade.symbol, int(trade.size),
                     trade.price, order_id, self.broker.__class__.__name__)
