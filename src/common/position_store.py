"""Position state storage.

BasePositionStore defines the interface; MongoPositionStore uses MongoDB,
InMemoryPositionStore uses a plain dict (for backtest/replay).
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from src.common.clock import utcnow
from src.common.collections import COLLECTION_POSITIONS


class BasePositionStore(ABC):
    """Interface for position storage backends."""

    @abstractmethod
    def set_positions(self, holdings: dict[str, datetime], entry_prices: dict[str, float] = None, session=None):
        pass

    @abstractmethod
    def open_position(self, symbol: str, entry_time: datetime, entry_price: float = 0.0, qty: int = 0, session=None):
        pass

    @abstractmethod
    def close_position(self, symbol: str, session=None):
        pass

    @abstractmethod
    def get_positions(self) -> dict[str, datetime]:
        pass

    @abstractmethod
    def get_positions_with_prices(self) -> dict[str, dict]:
        pass


class MongoPositionStore(BasePositionStore):
    """Read/write positions via MongoDB. One document per symbol."""

    def __init__(self, collection: str = COLLECTION_POSITIONS, db=None):
        try:
            if db is None:
                from src.data.utils.db_helper import get_db
                db = get_db()
            self._col = db[collection]
        except Exception:
            logger = logging.getLogger(__name__)
            logger.exception("Failed to connect to MongoDB for PositionStore")
            raise

    def set_positions(self, holdings: dict[str, datetime], entry_prices: dict[str, float] = None, session=None):
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
                **({"session": session} if session else {}),
            )
        if active:
            self._col.delete_many(
                {"symbol": {"$nin": list(active)}},
                **({"session": session} if session else {}),
            )
        else:
            self._col.delete_many({}, **({"session": session} if session else {}))

    def open_position(self, symbol: str, entry_time: datetime, entry_price: float = 0.0, qty: int = 0, session=None):
        """Atomically add a single position."""
        self._col.update_one(
            {"symbol": symbol},
            {"$set": {"symbol": symbol, "entryTime": entry_time.isoformat(),
                      "entryPrice": entry_price, "qty": qty, "updatedAt": utcnow()}},
            upsert=True,
            **({"session": session} if session else {}),
        )

    def close_position(self, symbol: str, session=None):
        """Atomically remove a single position."""
        self._col.delete_one(
            {"symbol": symbol},
            **({"session": session} if session else {}),
        )

    def get_positions(self) -> dict[str, datetime]:
        """Return {symbol: entry_time} for all open positions."""
        return {sym: info["entryTime"] for sym, info in self.get_positions_with_prices().items()}

    def get_positions_with_prices(self) -> dict[str, dict]:
        """Return {symbol: {entryTime, entryPrice, qty}} for all open positions."""
        return {
            doc["symbol"]: {
                "entryTime": datetime.fromisoformat(doc["entryTime"]),
                "entryPrice": doc.get("entryPrice", 0.0),
                "qty": doc.get("qty", 0),
            }
            for doc in self._col.find()
            if "entryTime" in doc
        }


# Backward-compatible alias
PositionStore = MongoPositionStore


class InMemoryPositionStore(BasePositionStore):
    """Positions backed by a plain dict — no MongoDB. For replay/backtest use."""

    def __init__(self):
        self._positions: dict[str, dict] = {}

    def set_positions(self, holdings: dict[str, datetime], entry_prices: dict[str, float] = None, session=None):
        prices = entry_prices or {}
        self._positions = {}
        for symbol, entry_time in holdings.items():
            self._positions[symbol] = {
                "entryTime": entry_time.isoformat(),
                "entryPrice": prices.get(symbol, 0.0),
                "qty": 0,
            }

    def open_position(self, symbol: str, entry_time: datetime, entry_price: float = 0.0, qty: int = 0, session=None):
        self._positions[symbol] = {
            "entryTime": entry_time.isoformat(),
            "entryPrice": entry_price,
            "qty": qty,
        }

    def close_position(self, symbol: str, session=None):
        self._positions.pop(symbol, None)

    def get_positions(self) -> dict[str, datetime]:
        return {sym: info["entryTime"] for sym, info in self.get_positions_with_prices().items()}

    def get_positions_with_prices(self) -> dict[str, dict]:
        return {
            sym: {
                "entryTime": datetime.fromisoformat(info["entryTime"]),
                "entryPrice": info.get("entryPrice", 0.0),
                "qty": info.get("qty", 0),
            }
            for sym, info in self._positions.items()
            if "entryTime" in info
        }
