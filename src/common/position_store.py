"""Position state backed by MongoDB — works in both single-process and distributed mode."""
from datetime import datetime
from src.data.utils.db_helper import get_mongo_client

COLLECTION = "positions"
DB = "EonTradingDB"


class PositionStore:
    """Read/write positions via MongoDB. One document per symbol."""

    def __init__(self):
        self._col = get_mongo_client()[DB][COLLECTION]

    def set_positions(self, holdings: dict[str, datetime]):
        """Upsert current holdings, remove closed positions."""
        active = set(holdings.keys())
        for symbol, entry_time in holdings.items():
            self._col.update_one(
                {"symbol": symbol},
                {"$set": {"symbol": symbol, "entryTime": entry_time.isoformat(), "updatedAt": datetime.utcnow()}},
                upsert=True,
            )
        self._col.delete_many({"symbol": {"$nin": list(active)}})

    def get_positions(self) -> dict[str, datetime]:
        """Return {symbol: entry_time} for all open positions."""
        return {
            doc["symbol"]: datetime.fromisoformat(doc["entryTime"])
            for doc in self._col.find()
            if "entryTime" in doc
        }
