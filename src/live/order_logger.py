"""Order logging — decoupled from TradeExecutor via dependency injection.

TradeExecutor calls `log_order(trade, order_id, broker_name)` without knowing
the backend.  The default implementation writes to MongoDB; pass a no-op or
custom logger to TradeExecutor for testing.
"""
import asyncio
import logging

from src.common.clock import utcnow
from src.common.events import TradeEvent
from src.data.utils.db_helper import get_mongo_client

logger = logging.getLogger(__name__)


async def noop_log_order(trade: TradeEvent, order_id: str, broker_name: str) -> None:
    """No-op — used in tests and when audit logging is disabled."""
    pass


async def mongo_log_order(trade: TradeEvent, order_id: str, broker_name: str) -> None:
    """Write order document to MongoDB orders collection."""
    try:
        col = get_mongo_client()["EonTradingDB"]["orders"]
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
        await asyncio.to_thread(col.insert_one, doc)
    except Exception:
        logger.debug("MongoDB unavailable, skipping order log")
