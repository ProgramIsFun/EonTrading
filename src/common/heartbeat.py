"""Component heartbeat — each runner writes its status to MongoDB periodically."""
import asyncio
import logging
import os
import platform
from abc import ABC, abstractmethod

from src.common.clock import utcnow
from src.common.collections import COLLECTION_HEARTBEATS

logger = logging.getLogger(__name__)


class BaseHeartbeatStore(ABC):
    """Interface for heartbeat storage backends."""

    @abstractmethod
    def beat(self, component: str, metadata: dict | None = None) -> None:
        """Write a heartbeat for the given component."""
        pass


class MongoHeartbeatStore(BaseHeartbeatStore):
    """MongoDB implementation of heartbeat storage."""

    def __init__(self, db=None):
        try:
            if db is None:
                from src.data.utils.db_helper import get_db
                db = get_db()
            self._col = db[COLLECTION_HEARTBEATS]
        except Exception as e:
            logger.warning("Heartbeat MongoDB unavailable: %s", e)
            self._col = None

    def beat(self, component: str, metadata: dict | None = None) -> None:
        if self._col is None:
            return
        self._col.update_one(
            {"component": component},
            {"$set": {
                "component": component,
                "lastBeat": utcnow(),
                "host": platform.node(),
                "pid": os.getpid(),
                **(metadata or {}),
            }},
            upsert=True,
        )


class Heartbeat:
    """Writes heartbeat to MongoDB every interval. Dashboard reads it to show component status."""

    def __init__(self, component: str, interval_sec: int = 30,
                 metadata: dict | None = None, store: BaseHeartbeatStore | None = None, db=None):
        self.component = component
        self.interval = interval_sec
        self.metadata = metadata or {}
        if store is not None:
            self._store = store
        elif db is not None:
            self._store = MongoHeartbeatStore(db)
        else:
            try:
                self._store = MongoHeartbeatStore()
            except Exception:
                self._store = None

    def beat(self):
        if self._store is None:
            return
        self._store.beat(self.component, self.metadata)

    async def run(self):
        """Background task — call once, runs forever."""
        while True:
            await asyncio.to_thread(self.beat)
            await asyncio.sleep(self.interval)

    @staticmethod
    def create_background(component: str, interval_sec: int = 30, metadata: dict | None = None):
        return asyncio.create_task(Heartbeat(component, interval_sec, metadata).run())
