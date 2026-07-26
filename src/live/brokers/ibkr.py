"""IBKRBroker — Interactive Brokers via ib_insync, confirms via callback."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.common.events import TradeEvent
from src.common.log_handler import ComponentFilter

from .broker import Broker, FillStatus

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("executor"))


class IBKRBroker(Broker):
    """pip install ib_insync

    Connects to TWS or IB Gateway. Confirmation via orderStatusEvent callback.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib: Any = None

    def _connect(self):
        if self._ib is not None and self._ib.isConnected():
            return
        try:
            from ib_insync import IB
            self._ib = IB()
            self._ib.connect(self.host, self.port, clientId=self.client_id)
        except Exception as e:
            raise ConnectionError(f"IBKR connect failed: {e}") from e

    async def execute(self, trade: TradeEvent) -> str | None:
        from ib_insync import MarketOrder, Stock
        try:
            self._connect()
            assert self._ib is not None
            contract = Stock(trade.symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)
            action = "BUY" if trade.action == "buy" else "SELL"
            order = MarketOrder(action, int(trade.size))
            ib_trade = self._ib.placeOrder(contract, order)

            # Wait for fill confirmation
            while not ib_trade.isDone():
                await asyncio.sleep(0.5)
                self._ib.sleep(0)

            order_id = str(ib_trade.order.orderId)
            return order_id
        except Exception as e:
            logger.error("IBKR order failed: %s — %s", trade.symbol, e)
            return None

    async def check_order(self, order_id: str) -> FillStatus:
        try:
            self._connect()
            assert self._ib is not None
            trades = self._ib.trades()
            for t in trades:
                if str(t.order.orderId) == order_id:
                    status = t.orderStatus.status
                    if status == "Filled":
                        return FillStatus(status="filled",
                                          filled_qty=int(t.orderStatus.filled),
                                          filled_price=t.orderStatus.avgFillPrice)
                    if status in ("Cancelled", "Inactive", "ApiCancelled"):
                        return FillStatus(status="cancelled", reason=status)
                    return FillStatus(status="pending")
            return FillStatus(status="pending")
        except Exception as e:
            logger.error("IBKR check_order error: %s", e)
            return FillStatus(status="pending")

    async def get_positions(self) -> dict[str, int]:
        try:
            self._connect()
            assert self._ib is not None
            return {p.contract.symbol: int(p.position) for p in self._ib.positions() if p.position > 0}
        except Exception as e:
            logger.error("IBKR get_positions error: %s", e)
            return {}

    async def get_cash(self) -> float:
        try:
            self._connect()
            assert self._ib is not None
            for av in self._ib.accountValues():
                if av.tag == "CashBalance" and av.currency == "USD":
                    return float(av.value)
        except Exception as e:
            logger.error("IBKR get_cash error: %s", e)
        return 0.0
