"""Persistent order tracking via MongoDB — survives crashes, centralizes order lifecycle."""
import asyncio
import logging
from datetime import datetime, timedelta

from src.common.clock import utcnow
from src.common.event_bus import EventBus
from src.common.position_store import PositionStore
from src.common.trade_store import trade_to_doc
from src.data.utils.db_helper import get_mongo_client

DB = "EonTradingDB"
COLLECTION = "pending_orders"

logger = logging.getLogger(__name__)


class OrderTracker:
    def __init__(
        self,
        bus: EventBus,
        broker,
        check_interval: float = 2.0,
        max_pending_age: float = 300.0,
        collection=None,
        position_store=None,
    ):
        self.bus = bus
        self.broker = broker
        self.check_interval = check_interval
        self.max_pending_age = max_pending_age
        self._col = collection or get_mongo_client()[DB][COLLECTION]
        self._position_store = position_store or PositionStore()
        self._ensure_indexes()

    def _ensure_indexes(self):
        self._col.create_index([("status", 1), ("next_check_at", 1)])
        self._col.create_index("placed_at", expireAfterSeconds=604800)

    async def run(self):
        while True:
            await asyncio.sleep(self.check_interval)
            await self._check_pending()

    async def _check_pending(self):
        now = utcnow()
        cursor = self._col.find({
            "status": "pending",
            "next_check_at": {"$lte": now},
        })
        cutoff = now - timedelta(seconds=self.max_pending_age)

        while True:
            doc = await asyncio.to_thread(lambda: next(cursor, None))
            if doc is None:
                break
            age = now - doc["placed_at"] if isinstance(doc["placed_at"], datetime) else utcnow() - doc["placed_at"]

            if age.total_seconds() > self.max_pending_age:
                await self._cancel(doc)
                continue

            try:
                status, reason = await self.broker.check_order(doc["order_id"])
            except NotImplementedError:
                logger.warning("Broker does not support check_order, skipping")
                continue
            except Exception as e:
                status, reason = "unknown", str(e)

            if status == "filled":
                await self._mark_filled(doc)
            elif status in ("cancelled", "failed", "rejected"):
                await self._mark_failed(doc, reason or status)
            else:
                self._col.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"next_check_at": now + timedelta(seconds=self.check_interval),
                              "checked_at": now, "retry_count": doc["retry_count"] + 1}},
                )

    async def _mark_filled(self, doc):
        now = utcnow()
        await asyncio.to_thread(
            self._col.update_one, {"_id": doc["_id"]},
            {"$set": {"status": "filled", "filled_at": now}},
        )

        symbol = doc["symbol"]
        action = doc["action"]
        price = float(doc["price"])
        shares = int(doc["shares"])

        ts = now.isoformat() + "Z"
        await asyncio.to_thread(
            get_mongo_client()[DB]["trades"].insert_one,
            trade_to_doc(symbol, action, price, shares, "filled", ts),
        )

        if action == "buy":
            entry_time = now.replace(microsecond=0)
            await asyncio.to_thread(self._position_store.open_position, symbol, entry_time, price)
        elif action == "sell":
            await asyncio.to_thread(self._position_store.close_position, symbol)

    async def _cancel(self, doc):
        try:
            await self.broker.cancel_order(doc["order_id"])
        except Exception as e:
            logger.warning("Failed to cancel order %s: %s", doc["order_id"], e)
        self._col.update_one({"_id": doc["_id"]},
                             {"$set": {"status": "timeout", "cancelled_at": utcnow(),
                                       "error": "max_pending_age exceeded"}})

    async def _mark_failed(self, doc, reason):
        self._col.update_one({"_id": doc["_id"]},
                             {"$set": {"status": "failed", "error": reason}})
