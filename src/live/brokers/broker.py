"""Broker interface.

To add a new broker:
  1. Subclass Broker
  2. Implement execute() — submit order, return order_id
  3. Implement check_order() — OrderTracker polls this to confirm fills
"""
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass

from src.common.events import TradeEvent

logger = logging.getLogger(__name__)


@dataclass
class FillStatus:
    """Result of a broker order status check."""
    status: str  # 'pending' | 'filled' | 'cancelled' | 'failed'
    reason: str | None = None
    filled_qty: int = 0
    filled_price: float = 0.0


@dataclass
class AccountInfo:
    """Unified account balance snapshot from any broker."""
    cash: float = 0.0
    buying_power: float = 0.0
    market_value: float = 0.0
    total_assets: float = 0.0


class Broker(ABC):
    """Interface for trade execute() submits the order and returns an order_id.
    OrderTracker polls check_order() to confirm fills or detect failures.

    Note on ISP: this is intentionally a fat interface (cancel, SL/TP stubs)
    because most real brokers implement all methods. Only PaperBroker stubs
    cancel and SL/TP — splitting into Broker+CancelCapable+SLTPCapable would
    add isinstance() checks everywhere just to accommodate one test broker.
    """

    def _connect(self):
        """Establish connection to the broker. Override in subclasses if needed."""
        pass

    @abstractmethod
    async def execute(self, trade: TradeEvent) -> str | None:
        """Submit a trade. Returns order_id for tracking, or None on failure."""
        pass

    async def check_order(self, order_id: str) -> FillStatus:
        """Returns fill status.
        status: 'pending' | 'filled' | 'cancelled' | 'failed'
        Override for brokers that use OrderTracker.
        """
        raise NotImplementedError

    async def cancel_order(self, order_id: str) -> bool:
        return False

    @abstractmethod
    async def get_positions(self) -> dict[str, int]:
        pass

    async def get_cash(self) -> float:
        """Returns available cash. Override for real brokers."""
        info = await self.get_account_info()
        return info.cash

    async def get_buying_power(self) -> float:
        """Returns available buying power. Defaults to cash if broker doesn't report it."""
        info = await self.get_account_info()
        return info.buying_power or info.cash

    async def get_account_info(self) -> AccountInfo:
        """Returns full account snapshot. Override in subclasses."""
        return AccountInfo(cash=0.0, buying_power=0.0)

    async def place_stop_loss(self, symbol: str, shares: int, stop_price: float) -> bool:
        return False

    async def place_take_profit(self, symbol: str, shares: int, target_price: float) -> bool:
        return False

    async def cancel_orders(self, symbol: str) -> bool:
        return False

    @asynccontextmanager
    async def _safe(self, operation: str):
        """Context manager: connects then yields; logs and re-raises on error.

        Usage in subclasses::

            async def execute(self, trade):
                try:
                    async with self._safe(f"execute({trade.symbol})"):
                        order = self._api.submit_order(...)
                        return str(order.id)
                except Exception:
                    return None
        """
        try:
            self._connect()
            yield
        except Exception as e:
            logger.error("%s.%s failed: %s", type(self).__name__, operation, e)
            raise
