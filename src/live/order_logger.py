"""Order logging — decoupled from TradeExecutor via dependency injection.

TradeExecutor calls `log_order(trade, order_id, broker_name)` without knowing
the backend.  The default implementation writes to MongoDB; pass a no-op or
custom logger to TradeExecutor for testing.
"""
import asyncio
import logging

from src.common.clock import utcnow
from src.common.events import TradeEvent
from src.common.order_store import BaseOrderStore, MongoOrderStore

logger = logging.getLogger(__name__)


async def noop_log_order(trade: TradeEvent, order_id: str, broker_name: str) -> None:
    """No-op — used in tests and when audit logging is disabled."""
    pass


async def mongo_log_order(trade: TradeEvent, order_id: str, broker_name: str, order_store: BaseOrderStore | None = None, db=None) -> None:
    """Write order document to the orders collection via BaseOrderStore."""
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
            "status": "pending",
            "placed_at": utcnow(),
            "checked_at": None,
            "filled_at": None,
            "cancelled_at": None,
            "next_check_at": utcnow(),
            "retry_count": 0,
            "error": None,
        }
        await asyncio.to_thread(order_store.insert, doc)
    except Exception:
        logger.warning("Failed to log order %s — MongoDB may be unavailable", order_id, exc_info=True)
