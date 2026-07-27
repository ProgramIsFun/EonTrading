"""Log store abstraction — BaseLogStore defines the interface,
MongoLogStore implements it with pymongo.
"""
from abc import ABC, abstractmethod

from src.common.collections import COLLECTION_LOGS
from src.common.mongo_base import MongoStoreBase


class BaseLogStore(ABC):
    """Interface for log storage backends."""

    @abstractmethod
    def find_logs(self, logger_name: str = "", level: str = "", limit: int = 100) -> list[dict]:
        """Query log entries with optional filters."""
        pass


class MongoLogStore(BaseLogStore, MongoStoreBase):
    """MongoDB implementation of log storage."""

    collection = COLLECTION_LOGS

    def find_logs(self, logger_name: str = "", level: str = "", limit: int = 100) -> list[dict]:
        q: dict = {}
        if logger_name:
            q["logger"] = {"$regex": f"^{logger_name}"}
        if level:
            q["level"] = level.upper()
        return list(self._col.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit))
