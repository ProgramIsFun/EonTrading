"""AlpacaBroker — Alpaca Markets (US), confirms by polling order status."""
import logging

from src.common.events import TradeEvent
from src.common.log_handler import ComponentFilter
from src.settings import settings

from .broker import Broker, FillStatus

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
        self._api = None

    def _connect(self):
        if self._api:
            return
        import alpaca_trade_api as tradeapi
        self._api = tradeapi.REST(self.api_key, self.secret_key, self.base_url, api_version="v2")

    async def execute(self, trade: TradeEvent) -> str | None:
        try:
            self._connect()
            order = self._api.submit_order(
                symbol=trade.symbol, qty=int(trade.size),
                side=trade.action, type="market", time_in_force="day",
            )
            return order.id
        except Exception as e:
            logger.error("Alpaca order failed: %s — %s", trade.symbol, e)
            return None

    async def check_order(self, order_id: str) -> FillStatus:
        try:
            self._connect()
            order = self._api.get_order(order_id)
            if order.status == "filled":
                return FillStatus(status="filled",
                                  filled_qty=int(float(order.filled_qty)),
                                  filled_price=float(order.filled_avg_price))
            if order.status in ("canceled", "expired", "rejected"):
                return FillStatus(status="cancelled", reason=order.status)
            return FillStatus(status="pending")
        except Exception as e:
            logger.error("Alpaca check_order error: %s", e)
            return FillStatus(status="pending")

    async def get_positions(self) -> dict[str, int]:
        try:
            self._connect()
            return {p.symbol: int(p.qty) for p in self._api.list_positions()}
        except Exception as e:
            logger.error("Alpaca get_positions error: %s", e)
            return {}

    async def get_cash(self) -> float:
        try:
            self._connect()
            return float(self._api.get_account().cash)
        except Exception as e:
            logger.error("Alpaca get_cash error: %s", e)
        return 0.0
