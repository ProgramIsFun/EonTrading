"""PaperBroker — dry run, instant fill."""
import asyncio
import logging
from uuid import uuid4

from src.common.events import TradeEvent
from src.common.log_handler import ComponentFilter
from src.common.price import get_price

from .broker import Broker, FillStatus

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("executor"))


class PaperBroker(Broker):
    """Dry-run broker — fills instantly. Optionally applies transaction costs."""

    def __init__(self, initial_cash: float = 100000, cost_model=None):
        self._positions: dict[str, int] = {}
        self._cash = initial_cash
        self.cost_model = cost_model

    async def execute(self, trade: TradeEvent) -> str | None:
        qty = int(trade.size)
        price = trade.price
        if price <= 0:
            price = await asyncio.to_thread(get_price, trade.symbol)
            if price <= 0:
                logger.error("Could not fetch price for %s, aborting", trade.symbol)
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
        return FillStatus(status="filled", filled_qty=0, filled_price=0.0)

    async def get_positions(self) -> dict[str, int]:
        return dict(self._positions)

    async def get_cash(self) -> float:
        return self._cash
