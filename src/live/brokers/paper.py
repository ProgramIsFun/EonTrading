"""PaperBroker — dry run, instant fill."""
import asyncio
import logging
from uuid import uuid4

from src.common.events import TradeEvent
from src.common.log_handler import ComponentFilter
from src.common.price import get_price

from .broker import AccountInfo, Broker, FillStatus

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("executor"))


class PaperBroker(Broker):
    """Dry-run broker — fills instantly. Optionally applies transaction costs."""

    def __init__(self, initial_cash: float = 100000, cost_model=None, order_store=None):
        self._positions: dict[str, int] = {}
        self._cash = initial_cash
        self.cost_model = cost_model
        self._order_store = order_store

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
            logger.info("📝 [DRY RUN] BUY %s %dsh @ $%.2f (fees: $%.2f) | %s", trade.symbol, qty, price, fees, trade.reason)
        elif trade.action == "sell":
            self._positions.pop(trade.symbol, None)
            proceeds = price * qty
            fees = self.cost_model.sell_cost(price, qty) if self.cost_model else 0
            self._cash += proceeds - fees
            logger.info("📝 [DRY RUN] SELL %s %dsh @ $%.2f (fees: $%.2f) | %s", trade.symbol, qty, price, fees, trade.reason)
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
