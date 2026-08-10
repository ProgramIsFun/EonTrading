"""Order logging — decoupled from the executing component via dependency injection.

The trader and the price monitor call `log_order(trade, order_id, broker_name)`
without knowing the backend.  The default implementation writes to MongoDB;
pass a no-op or custom logger for testing.
"""
import asyncio
import logging

from src.common.clock import utcnow
from src.common.events import TradeEvent
from src.common.order_store import BaseOrderStore, MongoOrderStore

logger = logging.getLogger(__name__)


async def noop_log_order(trade: TradeEvent, order_id: str | None, broker_name: str, **kwargs) -> None:
    """No-op — used in tests and when audit logging is disabled."""
    pass


async def mongo_log_order(
    trade: TradeEvent,
    order_id: str | None,
    broker_name: str,
    order_store: BaseOrderStore | None = None,
    db=None,
    status: str = "pending",
    error: str | None = None,
) -> None:
    """Write order document to the orders collection via BaseOrderStore.

    For failed orders, pass order_id=None, status="failed", error="<reason>".
    """
    try:
        if order_store is None:
            order_store = MongoOrderStore(db=db)
        doc = {
            "order_id": order_id,
            "broker_type": broker_name,
            "symbol": trade.symbol,
            "action": trade.action,
            "price": trade.price,
            "shares": trade.size,
            "reason": trade.reason,
            "timestamp": trade.timestamp,
            "status": status,
            "placed_at": utcnow() if order_id else None,
            "checked_at": None,
            "filled_at": None,
            "cancelled_at": None,
            "next_check_at": utcnow() if order_id else None,
            "retry_count": 0,
            "error": error,
        }
        await asyncio.to_thread(order_store.insert, doc)
        logger.info("Order logged: %s %s %s (order_id=%s, status=%s)",
                     trade.action, trade.symbol, broker_name, order_id, status)
    except Exception:
        logger.warning("Failed to log order %s — MongoDB may be unavailable", order_id, exc_info=True)
