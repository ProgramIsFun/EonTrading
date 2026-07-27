"""PaperBroker — dry run, instant fill with MongoDB-persisted cash."""
import asyncio
import logging
from uuid import uuid4

from src.common.events import TradeEvent
from src.common.log_handler import ComponentFilter
from src.common.price import get_price

from .broker import AccountInfo, Broker, FillStatus

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("executor"))

PAPER_ACCOUNT_ID = "paper_account"


class PaperBroker(Broker):
    """Dry-run broker — fills instantly. Optionally applies transaction costs.

    When ``persist_cash=True`` (default for live), cash is persisted to MongoDB
    ``paper_account`` collection so it survives restarts.
    Set ``persist_cash=False`` for tests or when persistence is not needed.
    """

    def __init__(self, initial_cash: float = 100000, cost_model=None, order_store=None,
                 persist_cash: bool = False):
        self._positions: dict[str, int] = {}
        self._initial_cash = initial_cash
        self._cash = initial_cash
        self.cost_model = cost_model
        self._order_store = order_store
        self._db = None
        self._persist_cash = persist_cash
        if persist_cash:
            self._load_cash()

    def _get_db(self):
        if self._db is None:
            from src.data.utils.db_helper import get_db
            self._db = get_db()
        return self._db

    def _load_cash(self):
        """Load cash from MongoDB. Create doc with initial_cash if not exists."""
        try:
            db = self._get_db()
            doc = db.paper_account.find_one({"_id": PAPER_ACCOUNT_ID})
            if doc:
                self._cash = float(doc["cash"])
                logger.info("Loaded paper cash: $%.2f from MongoDB", self._cash)
            else:
                db.paper_account.insert_one({
                    "_id": PAPER_ACCOUNT_ID,
                    "cash": self._initial_cash,
                })
                self._cash = self._initial_cash
                logger.info("Created paper account with $%.2f cash", self._initial_cash)
        except Exception:
            logger.warning("Failed to load paper cash from MongoDB, using $%.2f", self._initial_cash, exc_info=True)
            self._cash = self._initial_cash

    def _save_cash(self):
        """Persist current cash to MongoDB."""
        if not self._persist_cash:
            return
        try:
            db = self._get_db()
            db.paper_account.update_one(
                {"_id": PAPER_ACCOUNT_ID},
                {"$set": {"cash": self._cash}},
                upsert=True,
            )
        except Exception:
            logger.error("Failed to save paper cash to MongoDB", exc_info=True)

    async def execute(self, trade: TradeEvent) -> str | None:
        qty = int(trade.size)
        price = trade.price
        if price <= 0:
            price = await asyncio.to_thread(get_price, trade.symbol)
            if price <= 0:
                logger.error("Could not fetch price for %s, aborting", trade.symbol, exc_info=True)
                return None
        if trade.action == "buy":
            cost = price * qty
            fees = self.cost_model.buy_cost(price, qty) if self.cost_model else 0
            total = cost + fees
            self._cash -= total
            self._positions[trade.symbol] = self._positions.get(trade.symbol, 0) + qty
            self._save_cash()
            logger.info("📝 [DRY RUN] BUY %s %dsh @ $%.2f (fees: $%.2f) | cash=$%.2f | %s",
                        trade.symbol, qty, price, fees, self._cash, trade.reason)
        elif trade.action == "sell":
            self._positions.pop(trade.symbol, None)
            proceeds = price * qty
            fees = self.cost_model.sell_cost(price, qty) if self.cost_model else 0
            self._cash += proceeds - fees
            self._save_cash()
            logger.info("📝 [DRY RUN] SELL %s %dsh @ $%.2f (fees: $%.2f) | cash=$%.2f | %s",
                        trade.symbol, qty, price, fees, self._cash, trade.reason)
        return f"paper-{trade.symbol}-{uuid4().hex[:8]}"

    async def check_order(self, order_id: str) -> FillStatus:
        if self._order_store is None:
            from src.common.order_store import MongoOrderStore
            self._order_store = MongoOrderStore()
        doc = await asyncio.to_thread(self._order_store.find_by_order_id, order_id)
        if doc and doc.get("status") == "pending":
            return FillStatus(
                status="filled",
                filled_qty=int(doc["shares"]),
                filled_price=float(doc["price"]),
            )
        return FillStatus(status="unknown")

    async def get_positions(self) -> dict[str, int]:
        return dict(self._positions)

    async def get_account_info(self) -> AccountInfo:
        return AccountInfo(
            cash=self._cash,
            buying_power=self._cash,
        )
