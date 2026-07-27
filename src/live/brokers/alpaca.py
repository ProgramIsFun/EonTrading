"""AlpacaBroker — Alpaca Markets (US), confirms by polling order status."""
from __future__ import annotations

import logging
from typing import Any

from src.common.events import TradeEvent
from src.common.log_handler import ComponentFilter
from src.settings import settings

from .broker import AccountInfo, Broker, FillStatus

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("executor"))


class AlpacaBroker(Broker):
    """pip install alpaca-trade-api

    Uses Alpaca paper or live trading API.
    """

    def __init__(self, api_key: str = "", secret_key: str = "", paper: bool = True):
        self.api_key = api_key or settings.alpaca_api_key
        self.secret_key = secret_key or settings.alpaca_secret_key
        self.base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        self._api: Any = None
        mode = "PAPER" if paper else "LIVE"
        logger.info("AlpacaBroker initialized in %s mode", mode)

    def _connect(self):
        if self._api is not None:
            return
        try:
            import alpaca_trade_api as tradeapi
            self._api = tradeapi.REST(self.api_key, self.secret_key, self.base_url, api_version="v2")
        except Exception as e:
            raise ConnectionError(f"Alpaca connect failed: {e}") from e

    async def execute(self, trade: TradeEvent) -> str | None:
        try:
            async with self._safe(f"execute({trade.symbol})"):
                assert self._api is not None
                order = self._api.submit_order(
                    symbol=trade.symbol, qty=int(trade.size),
                    side=trade.action, type="market", time_in_force="day",
                )
                return str(order.id)
        except Exception:
            return None

    async def check_order(self, order_id: str) -> FillStatus:
        try:
            async with self._safe(f"check_order({order_id})"):
                assert self._api is not None
                order = self._api.get_order(order_id)
                if order.status == "filled":
                    return FillStatus(status="filled",
                                      filled_qty=int(float(order.filled_qty)),
                                      filled_price=float(order.filled_avg_price))
                if order.status in ("canceled", "expired", "rejected"):
                    return FillStatus(status="cancelled", reason=order.status)
                return FillStatus(status="pending")
        except Exception:
            return FillStatus(status="pending")

    async def get_positions(self) -> dict[str, int]:
        try:
            async with self._safe("get_positions"):
                assert self._api is not None
                return {p.symbol: int(p.qty) for p in self._api.list_positions()}
        except Exception:
            return {}

    async def get_account_info(self) -> AccountInfo:
        try:
            async with self._safe("get_account_info"):
                assert self._api is not None
                acct = self._api.get_account()
                return AccountInfo(
                    cash=float(acct.cash),
                    buying_power=float(acct.buying_power),
                    market_value=float(acct.portfolio_value) - float(acct.cash),
                    total_assets=float(acct.portfolio_value),
                )
        except Exception:
            return AccountInfo()
