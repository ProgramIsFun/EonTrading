"""Component heartbeat — each runner writes its status to MongoDB periodically."""
import asyncio
import os
import platform
from datetime import datetime


COLLECTION = "heartbeats"
DB = "EonTradingDB"


class Heartbeat:
    """Writes heartbeat to MongoDB every interval. Dashboard reads it to show component status."""

    def __init__(self, component: str, interval_sec: int = 30, metadata: dict = None):
        self.component = component
        self.interval = interval_sec
        self.metadata = metadata or {}
        self._col = None
        try:
            from src.data.utils.db_helper import get_mongo_client
            self._col = get_mongo_client()[DB][COLLECTION]
        except Exception:
            pass

    def beat(self):
        if not self._col:
            return
        self._col.update_one(
            {"component": self.component},
            {"$set": {
                "component": self.component,
                "lastBeat": datetime.utcnow(),
                "host": platform.node(),
                "pid": os.getpid(),
                **self.metadata,
            }},
            upsert=True,
        )

    async def run(self):
        """Background task — call once, runs forever."""
        while True:
            self.beat()
            await asyncio.sleep(self.interval)
