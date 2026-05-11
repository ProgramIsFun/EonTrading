"""Position state backed by MongoDB — works in both single-process and distributed mode."""
from datetime import datetime

from src.common.clock import utcnow
from src.data.utils.db_helper import get_mongo_client

COLLECTION = "positions"
DB = "EonTradingDB"


class PositionStore:
    """Read/write positions via MongoDB. One document per symbol."""

    def __init__(self, collection: str = "positions"):
        self._col = get_mongo_client()[DB][collection]

    def set_positions(self, holdings: dict[str, datetime], entry_prices: dict[str, float] = None):
        """Sync holdings to MongoDB — upsert active, remove closed."""
        prices = entry_prices or {}
        active = set(holdings.keys())
        for symbol, entry_time in holdings.items():
            fields = {"entryTime": entry_time.isoformat(), "updatedAt": utcnow()}
            if symbol in prices:
                fields["entryPrice"] = prices[symbol]
            self._col.update_one(
                {"symbol": symbol},
                {"$set": fields},
                upsert=True,
            )
        if active:
            self._col.delete_many({"symbol": {"$nin": list(active)}})
        else:
            self._col.delete_many({})

    def open_position(self, symbol: str, entry_time: datetime, entry_price: float = 0.0):
        """Atomically add a single position."""
        self._col.update_one(
            {"symbol": symbol},
            {"$set": {"symbol": symbol, "entryTime": entry_time.isoformat(),
                      "entryPrice": entry_price, "updatedAt": utcnow()}},
            upsert=True,
        )

    def close_position(self, symbol: str):
        """Atomically remove a single position."""
        self._col.delete_one({"symbol": symbol})

    def get_positions(self) -> dict[str, datetime]:
        """Return {symbol: entry_time} for all open positions."""
        return {
            doc["symbol"]: datetime.fromisoformat(doc["entryTime"])
            for doc in self._col.find()
            if "entryTime" in doc
        }

    def get_positions_with_prices(self) -> dict[str, dict]:
        """Return {symbol: {entryTime, entryPrice}} for all open positions."""
        return {
            doc["symbol"]: {
                "entryTime": datetime.fromisoformat(doc["entryTime"]),
                "entryPrice": doc.get("entryPrice", 0.0),
            }
            for doc in self._col.find()
            if "entryTime" in doc
        }
