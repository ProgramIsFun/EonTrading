"""Portfolio context abstraction.

Defines a single canonical snapshot of "what we own and what we recently did"
(positions + recent orders) plus a PortfolioSource interface with two pluggable
backends:

- MongoPortfolioSource  → reads our own MongoDB (positions + orders collections)
- BrokerPortfolioSource → makes fresh calls to the live broker API

Pick one via ``PORTFOLIO_SOURCE=db|broker`` (settings.portfolio_source) or by
calling ``build_portfolio_source()``.  Consumers (e.g. the LLM sentiment
analyzer) only ever see a ``PortfolioSnapshot``, so switching the backend later
(e.g. from our DB to a fresh broker poll) is a config change, not a code change.
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from src.common.clock import utcnow

logger = logging.getLogger(__name__)


@dataclass
class PositionInfo:
    symbol: str
    qty: int = 0
    entry_price: float = 0.0
    entry_time: datetime | None = None
    peak_price: float = 0.0


@dataclass
class OrderInfo:
    symbol: str
    action: str  # "buy" | "sell"
    qty: int = 0
    price: float = 0.0
    status: str = ""
    order_id: str = ""
    placed_at: datetime | None = None
    filled_at: datetime | None = None


@dataclass
class PortfolioSnapshot:
    """Canonical portfolio context, independent of where it came from."""
    source: str  # "db" | "broker"
    as_of: datetime
    cash: float = 0.0
    positions: list[PositionInfo] = field(default_factory=list)
    recent_orders: list[OrderInfo] = field(default_factory=list)  # newest first

    def positions_by_symbol(self) -> dict[str, PositionInfo]:
        return {p.symbol: p for p in self.positions}


class PortfolioSource(ABC):
    """Interface for fetching portfolio context."""

    @abstractmethod
    async def get_snapshot(self) -> PortfolioSnapshot:
        pass


def _parse_dt(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


class MongoPortfolioSource(PortfolioSource):
    """Reads positions + recent orders from our own MongoDB."""

    def __init__(self, position_store=None, order_store=None, db=None, limit: int = 20):
        self._position_store = position_store
        self._order_store = order_store
        self._db = db
        self.limit = limit

    def _get_db(self):
        if self._db is None:
            from src.data.utils.db_helper import get_db
            self._db = get_db()
        return self._db

    def _get_position_store(self):
        if self._position_store is None:
            from src.common.position_store import MongoPositionStore
            self._position_store = MongoPositionStore(db=self._get_db())
        return self._position_store

    def _get_order_store(self):
        if self._order_store is None:
            from src.common.order_store import MongoOrderStore
            self._order_store = MongoOrderStore(db=self._get_db())
        return self._order_store

    def _load(self) -> PortfolioSnapshot:
        positions = self._get_position_store().get_positions_with_prices()
        orders = self._get_order_store().find_recent(limit=self.limit)
        cash = 0.0
        try:
            doc = self._get_db().paper_account.find_one({"_id": "paper_account"})
            if doc:
                cash = float(doc.get("cash", 0.0))
        except Exception:
            logger.warning("Failed to read paper account cash for portfolio snapshot", exc_info=True)
        return PortfolioSnapshot(
            source="db",
            as_of=utcnow(),
            cash=cash,
            positions=[
                PositionInfo(
                    symbol=symbol,
                    qty=int(info.get("qty", 0)),
                    entry_price=float(info.get("entryPrice", 0.0)),
                    entry_time=_parse_dt(info.get("entryTime")),
                    peak_price=float(info.get("peakPrice", info.get("entryPrice", 0.0))),
                )
                for symbol, info in positions.items()
            ],
            recent_orders=[
                OrderInfo(
                    symbol=doc.get("symbol", ""),
                    action=doc.get("action", ""),
                    qty=int(doc.get("shares", 0)),
                    price=float(doc.get("price", 0.0)),
                    status=doc.get("status", ""),
                    order_id=doc.get("order_id", ""),
                    placed_at=_parse_dt(doc.get("placed_at")),
                    filled_at=_parse_dt(doc.get("filled_at")),
                )
                for doc in orders
            ],
        )

    async def get_snapshot(self) -> PortfolioSnapshot:
        return await asyncio.to_thread(self._load)


class BrokerPortfolioSource(PortfolioSource):
    """Fresh calls to the broker API — no local state involved."""

    def __init__(self, broker, limit: int = 20):
        self.broker = broker
        self.limit = limit

    async def get_snapshot(self) -> PortfolioSnapshot:
        account = await self.broker.get_account_info()
        positions = await self.broker.get_positions()
        orders = await self.broker.get_recent_orders(self.limit)
        return PortfolioSnapshot(
            source="broker",
            as_of=utcnow(),
            cash=account.cash,
            positions=[
                PositionInfo(symbol=symbol, qty=int(qty))
                for symbol, qty in positions.items()
            ],
            recent_orders=[
                OrderInfo(
                    symbol=doc.get("symbol", ""),
                    action=doc.get("action", ""),
                    qty=int(doc.get("qty", doc.get("shares", 0))),
                    price=float(doc.get("price", 0.0)),
                    status=doc.get("status", ""),
                    order_id=doc.get("order_id", ""),
                    placed_at=_parse_dt(doc.get("placed_at")),
                    filled_at=_parse_dt(doc.get("filled_at")),
                )
                for doc in orders
            ],
        )


def build_portfolio_source(source: str | None = None) -> PortfolioSource:
    """Build a PortfolioSource from ``PORTFOLIO_SOURCE`` (default "db").

    - "db"     → MongoPortfolioSource (reads our MongoDB)
    - "broker" → BrokerPortfolioSource (fresh broker API calls)
    """
    from src.settings import settings

    name = (source or settings.portfolio_source or "db").strip().lower()
    if name == "broker":
        from src.common.factories import build_broker
        return BrokerPortfolioSource(build_broker())
    return MongoPortfolioSource()
