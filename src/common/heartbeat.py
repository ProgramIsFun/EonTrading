"""Component heartbeat — each runner writes its status to MongoDB periodically."""
import asyncio
import logging
import os
import platform

from src.common.clock import utcnow
from src.common.collections import COLLECTION_HEARTBEATS

logger = logging.getLogger(__name__)


COLLECTION = COLLECTION_HEARTBEATS


class Heartbeat:
    """Writes heartbeat to MongoDB every interval. Dashboard reads it to show component status."""

    def __init__(self, component: str, interval_sec: int = 30, metadata: dict = None, db=None):
        self.component = component
        self.interval = interval_sec
        self.metadata = metadata or {}
        self._col = None
        try:
            if db is None:
                from src.data.utils.db_helper import get_db
                db = get_db()
            self._col = db[COLLECTION]
        except Exception as e:
            logger.warning("Heartbeat MongoDB unavailable: %s", e)

    def beat(self):
        if self._col is None:
            return
        self._col.update_one(
            {"component": self.component},
            {"$set": {
                "component": self.component,
                "lastBeat": utcnow(),
                "host": platform.node(),
                "pid": os.getpid(),
                **self.metadata,
            }},
            upsert=True,
        )

    async def run(self):
        """Background task — call once, runs forever."""
        while True:
            await asyncio.to_thread(self.beat)
            await asyncio.sleep(self.interval)

    @staticmethod
    def create_background(component: str, interval_sec: int = 30, metadata: dict = None):
        return asyncio.create_task(Heartbeat(component, interval_sec, metadata).run())
