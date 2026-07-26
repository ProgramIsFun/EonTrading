"""Log store abstraction — BaseLogStore defines the interface,
MongoLogStore implements it with pymongo.
"""
import logging
from abc import ABC, abstractmethod

from src.common.collections import COLLECTION_LOGS

logger = logging.getLogger(__name__)


class BaseLogStore(ABC):
    """Interface for log storage backends."""

    @abstractmethod
    def find_logs(self, logger_name: str = "", level: str = "", limit: int = 100) -> list[dict]:
        """Query log entries with optional filters."""
        pass


class MongoLogStore(BaseLogStore):
    """MongoDB implementation of log storage."""

    def __init__(self, db=None):
        try:
            if db is None:
                from src.data.utils.db_helper import get_db
                db = get_db()
            self._col = db[COLLECTION_LOGS]
        except Exception:
            logger.exception("Failed to connect to MongoDB for LogStore")
            raise

    def find_logs(self, logger_name: str = "", level: str = "", limit: int = 100) -> list[dict]:
        q: dict = {}
        if logger_name:
            q["logger"] = {"$regex": f"^{logger_name}"}
        if level:
            q["level"] = level.upper()
        return list(self._col.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit))
