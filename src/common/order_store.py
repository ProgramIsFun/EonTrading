"""Order store abstraction — BaseOrderStore defines the interface,
MongoOrderStore implements it with pymongo.

FUTURE: Add PostgresOrderStore, SqliteOrderStore, etc. by implementing
the same BaseOrderStore ABC. OrderTracker and order_logger never change.
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from src.common.clock import utcnow
from src.common.collections import COLLECTION_ORDERS

logger = logging.getLogger(__name__)


class BaseOrderStore(ABC):
    """Interface for order storage backends."""

    @abstractmethod
    def find_pending(self, now: datetime) -> list[dict]:
        """Return pending orders whose next_check_at <= now."""
        pass

    @abstractmethod
    def mark_filled(self, mongo_id, fill_time: datetime) -> None:
        """Set order status to 'filled'."""
        pass

    @abstractmethod
    def mark_failed(self, mongo_id, reason: str) -> None:
        """Set order status to 'failed'."""
        pass

    @abstractmethod
    def mark_timeout(self, mongo_id, error: str) -> None:
        """Set order status to 'timeout'."""
        pass

    @abstractmethod
    def update_retry(self, mongo_id, next_check: datetime, checked_at: datetime, retry_count: int) -> None:
        """Update retry fields for a pending order."""
        pass

    @abstractmethod
    def insert(self, doc: dict) -> None:
        """Insert a new order document."""
        pass

    @abstractmethod
    def ensure_indexes(self) -> None:
        """Create required indexes (idempotent)."""
        pass


class MongoOrderStore(BaseOrderStore):
    """MongoDB implementation of BaseOrderStore."""

    def __init__(self, collection=None, db=None):
        try:
            if collection is not None:
                self._col = collection
            else:
                if db is None:
                    from src.data.utils.db_helper import get_db
                    db = get_db()
                self._col = db[COLLECTION_ORDERS]
        except Exception:
            logger.exception("Failed to connect to MongoDB for OrderStore")
            raise

    def find_pending(self, now: datetime) -> list[dict]:
        return list(self._col.find({
            "status": "pending",
            "next_check_at": {"$lte": now},
        }))

    def mark_filled(self, mongo_id, fill_time: datetime) -> None:
        self._col.update_one(
            {"_id": mongo_id},
            {"$set": {"status": "filled", "filled_at": fill_time}},
        )

    def mark_failed(self, mongo_id, reason: str) -> None:
        self._col.update_one(
            {"_id": mongo_id},
            {"$set": {"status": "failed", "error": reason}},
        )

    def mark_timeout(self, mongo_id, error: str) -> None:
        self._col.update_one(
            {"_id": mongo_id},
            {"$set": {"status": "timeout", "cancelled_at": utcnow(), "error": error}},
        )

    def update_retry(self, mongo_id, next_check: datetime, checked_at: datetime, retry_count: int) -> None:
        self._col.update_one(
            {"_id": mongo_id},
            {"$set": {"next_check_at": next_check, "checked_at": checked_at, "retry_count": retry_count}},
        )

    def insert(self, doc: dict) -> None:
        self._col.insert_one(doc)

    def ensure_indexes(self) -> None:
        self._col.create_index([("status", 1), ("next_check_at", 1)])
        self._col.create_index("placed_at", expireAfterSeconds=604800)
