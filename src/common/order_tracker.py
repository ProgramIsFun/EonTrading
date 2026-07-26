"""Persistent order tracking via MongoDB — survives crashes, centralizes order lifecycle."""
import asyncio
import logging
from datetime import timedelta

from src.common.clock import utcnow
from src.common.log_handler import ComponentFilter
from src.common.event_bus import EventBus
from src.common.order_store import BaseOrderStore, MongoOrderStore
from src.common.position_store import PositionStore
from src.live.brokers.broker import FillStatus

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("order_tracker"))


class OrderTracker:
    def __init__(
        self,
        bus: EventBus,
        broker,
        check_interval: float = 2.0,
        max_pending_age: float = 300.0,
        order_store: BaseOrderStore | None = None,
        position_store=None,
        db=None,
    ):
        self.bus = bus
        self.broker = broker
        self.check_interval = check_interval
        self.max_pending_age = max_pending_age
        self._store = order_store or MongoOrderStore(db=db)
        self._position_store = position_store or PositionStore(db=db)
        self._store.ensure_indexes()

    async def run(self):
        while True:
            await asyncio.sleep(self.check_interval)
            await self._check_pending()

    async def _check_pending(self):
        now = utcnow()
        cutoff = now - timedelta(seconds=self.max_pending_age)

        docs = await asyncio.to_thread(self._store.find_pending, now)

        for doc in docs:
            age = now - doc["placed_at"]

            if age.total_seconds() > self.max_pending_age:
                await self._cancel(doc)
                continue

            try:
                fill = await self.broker.check_order(doc["order_id"])
            except NotImplementedError:
                logger.warning("Broker does not support check_order, skipping")
                continue
            except Exception as e:
                logger.warning("Broker check_order failed for %s: %s", doc.get("order_id"), e)
                fill = FillStatus(status="unknown", reason=str(e))

            if fill.status == "filled" and fill.filled_qty >= int(doc["shares"]):
                await self._mark_filled(doc, fill)
            elif fill.status in ("cancelled", "failed", "rejected"):
                await self._mark_failed(doc, fill.reason or fill.status)
            else:
                await asyncio.to_thread(
                    self._store.update_retry, doc["_id"],
                    now + timedelta(seconds=self.check_interval),
                    now, doc["retry_count"] + 1,
                )

    async def _mark_filled(self, doc, fill: FillStatus):
        now = utcnow()
        await asyncio.to_thread(self._store.mark_filled, doc["_id"], now)

        symbol = doc["symbol"]
        action = doc["action"]
        price = fill.filled_price if fill.filled_price > 0 else float(doc["price"])
        shares = int(doc["shares"])

        if action == "buy":
            entry_time = now.replace(microsecond=0)
            await asyncio.to_thread(self._position_store.open_position, symbol, entry_time, price, shares)
        elif action == "sell":
            await asyncio.to_thread(self._position_store.close_position, symbol)

    async def _cancel(self, doc):
        try:
            await self.broker.cancel_order(doc["order_id"])
        except Exception as e:
            logger.warning("Failed to cancel order %s: %s", doc["order_id"], e)
        await asyncio.to_thread(
            self._store.mark_timeout, doc["_id"], "max_pending_age exceeded",
        )

    async def _mark_failed(self, doc, reason):
        await asyncio.to_thread(self._store.mark_failed, doc["_id"], reason)
