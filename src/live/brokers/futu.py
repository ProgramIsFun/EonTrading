"""FutuBroker — HK/US market via Futu OpenD.

  confirm_mode="poll" (default): polls order status every N seconds
  confirm_mode="callback": uses TradeOrderHandlerBase for real-time updates
"""
import asyncio
import logging

from src.common.events import TradeEvent
from src.common.log_handler import ComponentFilter

from .broker import Broker

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("executor"))


class FutuBroker(Broker):
    """pip install futu-api

    confirm_mode:
      "poll" (default) — simple, reliable, works in simulate mode
      "callback" — real-time order status via Futu push, lower latency
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 11111, simulate: bool = True,
                 confirm_mode: str = "poll", poll_interval: float = 2.0, poll_timeout: float = 60.0):
        self.host = host
        self.port = port
        self.simulate = simulate
        self.confirm_mode = confirm_mode
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout
        self._ctx = None

    def _get_ctx(self):
        from futu import OpenSecTradeContext
        if not self._ctx:
            self._ctx = OpenSecTradeContext(host=self.host, port=self.port)
        return self._ctx

    @staticmethod
    def _to_futu_code(symbol: str) -> str:
        """Convert standard format to Futu native: '0700.HK' → 'HK.00700'."""
        if "." in symbol:
            ticker, exchange = symbol.split(".", 1)
            if exchange == "HK":
                ticker = ticker.zfill(5)
            return f"{exchange}.{ticker}"
        return symbol

    @staticmethod
    def _from_futu_code(code: str) -> str:
        """Convert Futu native to standard format: 'HK.00700' → '00700.HK'."""
        if "." in code:
            exchange, ticker = code.split(".", 1)
            return f"{ticker}.{exchange}"
        return code

    async def execute(self, trade: TradeEvent) -> str | None:
        from futu import TrdEnv, TrdSide, OrderType
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        trd_side = TrdSide.BUY if trade.action == "buy" else TrdSide.SELL
        futu_code = self._to_futu_code(trade.symbol)
        try:
            ctx = await asyncio.to_thread(self._get_ctx)

            def _place():
                if trade.action == "sell":
                    return ctx.place_order(
                        price=trade.price, qty=int(trade.size),
                        code=futu_code, trd_side=trd_side, trd_env=trd_env,
                        order_type=OrderType.MARKET,
                    )
                return ctx.place_order(
                    price=trade.price, qty=int(trade.size),
                    code=futu_code, trd_side=trd_side, trd_env=trd_env,
                )
            ret, data = await asyncio.to_thread(_place)
            if ret != 0:
                logger.error("Futu order rejected: %s %s — %s", trade.action.upper(), trade.symbol, data)
                return None
            order_id = str(data["order_id"].iloc[0])
            logger.info("📤 Futu order placed: %s %s (id=%s)", trade.action.upper(), trade.symbol, order_id)
            return order_id
        except Exception as e:
            logger.error("Futu order failed: %s — %s", trade.symbol, e)
            return None

    async def check_order(self, order_id: str) -> tuple[str, str | None]:
        from futu import OrderStatus, TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            ctx = await asyncio.to_thread(self._get_ctx)

            def _query():
                return ctx.order_list_query(order_id=int(order_id), trd_env=trd_env)
            ret, orders = await asyncio.to_thread(_query)
            if ret != 0:
                logger.warning("Futu check_order query failed: %s", orders)
                return "pending", None
            status = orders["order_status"].iloc[0]
            if status in (OrderStatus.FILLED_ALL, OrderStatus.FILLED_PART):
                return "filled", None
            if status in (OrderStatus.CANCELLED_ALL, OrderStatus.FAILED, OrderStatus.DELETED):
                return "cancelled", f"status: {status}"
            return "pending", None
        except Exception as e:
            logger.error("Futu check_order error: %s", e)
            return "pending", None

    async def cancel_order(self, order_id: str) -> bool:
        from futu import TrdEnv, ModifyOrderOp
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            ctx = await asyncio.to_thread(self._get_ctx)

            def _cancel():
                return ctx.modify_order(
                    ModifyOrderOp.CANCEL,
                    order_id=int(order_id),
                    qty=0,
                    price=0,
                    trd_env=trd_env,
                )
            ret, msg = await asyncio.to_thread(_cancel)
            if ret != 0:
                logger.warning("Futu cancel_order failed: %s", msg)
            return ret == 0
        except Exception as e:
            logger.error("Futu cancel_order error: %s", e)
            return False

    async def get_positions(self) -> dict[str, int]:
        from futu import TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            ctx = await asyncio.to_thread(self._get_ctx)

            def _query():
                return ctx.position_list_query(trd_env=trd_env)
            ret, data = await asyncio.to_thread(_query)
            if ret != 0:
                logger.warning("Futu get_positions failed: %s", data)
                return {}
            return {self._from_futu_code(row["code"]): int(row["qty"]) for _, row in data.iterrows() if int(row["qty"]) > 0}
        except Exception as e:
            logger.error("Futu get_positions error: %s", e)
            return {}

    async def get_cash(self) -> float:
        from futu import TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            ctx = await asyncio.to_thread(self._get_ctx)

            def _query():
                return ctx.accinfo_query(trd_env=trd_env)
            ret, data = await asyncio.to_thread(_query)
            if ret == 0:
                return float(data["cash"].iloc[0])
            logger.warning("Futu get_cash failed: %s", data)
        except Exception as e:
            logger.error("Futu get_cash error: %s", e)
        return 0.0
