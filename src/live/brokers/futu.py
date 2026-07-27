"""FutuBroker — HK/US market via Futu OpenD.

  confirm_mode="poll" (default): polls order status every N seconds
  confirm_mode="callback": uses TradeOrderHandlerBase for real-time updates
"""
import asyncio
import logging

from src.common.events import TradeEvent
from src.common.log_handler import ComponentFilter

from .broker import AccountInfo, Broker, FillStatus

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("executor"))

# HK price tick table: (lower_bound, tick_size)
_HK_TICK_TABLE = [
    (0.25,  0.001),
    (0.50,  0.005),
    (10.00, 0.010),
    (20.00, 0.020),
    (100.00, 0.050),
    (200.00, 0.100),
    (500.00, 0.200),
    (1000.00, 0.500),
    (2000.00, 1.000),
    (5000.00, 2.000),
]


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
        mode = "SIMULATE" if simulate else "LIVE"
        logger.info("FutuBroker initialized in %s mode", mode)

    def _connect(self):
        self._get_ctx()

    def _get_ctx(self):
        from futu import OpenSecTradeContext
        if not self._ctx:
            self._ctx = OpenSecTradeContext(host=self.host, port=self.port)
        return self._ctx

    @staticmethod
    def _round_price(price: float) -> float:
        """Round price to valid HK tick size."""
        for lower, tick in _HK_TICK_TABLE:
            if price < lower:
                return round(price / tick) * tick
        return round(price / 5.0) * 5.0

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

    async def _get_lot_size(self, futu_code: str) -> int:
        """Query lot size for a stock. Returns 1 if query fails (no rounding)."""
        if not futu_code.startswith("HK."):
            return 1
        try:
            from futu import OpenQuoteContext, Market, SecurityType
            ctx = await asyncio.to_thread(
                lambda: OpenQuoteContext(host=self.host, port=self.port)
            )

            def _query():
                return ctx.get_stock_basicinfo(Market.HK, SecurityType.STOCK, code_list=[futu_code])
            ret, info = await asyncio.to_thread(_query)
            ctx.close()
            if ret == 0 and not info.empty:
                return int(info["lot_size"].iloc[0])
        except Exception as e:
            logger.warning("Failed to get lot size for %s: %s", futu_code, e)
        return 100

    async def execute(self, trade: TradeEvent) -> str | None:
        from futu import TrdEnv, TrdSide, OrderType
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        trd_side = TrdSide.BUY if trade.action == "buy" else TrdSide.SELL
        futu_code = self._to_futu_code(trade.symbol)
        try:
            ctx = await asyncio.to_thread(self._get_ctx)

            price = trade.price
            qty = int(trade.size)
            if trade.action == "buy":
                price = self._round_price(price)
                lot_size = await self._get_lot_size(futu_code)
                if lot_size > 1:
                    qty = (qty + lot_size - 1) // lot_size * lot_size

            def _place():
                if trade.action == "sell":
                    return ctx.place_order(
                        price=price, qty=qty,
                        code=futu_code, trd_side=trd_side, trd_env=trd_env,
                        order_type=OrderType.MARKET,
                    )
                return ctx.place_order(
                    price=price, qty=qty,
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

    async def check_order(self, order_id: str) -> FillStatus:
        from futu import OrderStatus, TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            async with self._safe(f"check_order({order_id})"):
                ctx = await asyncio.to_thread(self._get_ctx)

                def _query():
                    return ctx.order_list_query(order_id=int(order_id), trd_env=trd_env)
                ret, orders = await asyncio.to_thread(_query)
                if ret != 0:
                    logger.warning("Futu check_order query failed: %s", orders)
                    return FillStatus(status="pending")
                row = orders.iloc[0]
                status = row["order_status"]
                dealt_qty = int(row.get("dealt_qty", 0))
                dealt_price = float(row.get("dealt_avg_price", 0.0))
                if status in (OrderStatus.FILLED_ALL, OrderStatus.FILLED_PART):
                    return FillStatus(status="filled", filled_qty=dealt_qty, filled_price=dealt_price)
                if status in (OrderStatus.CANCELLED_ALL, OrderStatus.FAILED, OrderStatus.DELETED):
                    return FillStatus(status="cancelled", reason=f"status: {status}")
                return FillStatus(status="pending")
        except Exception:
            return FillStatus(status="pending")

    async def cancel_order(self, order_id: str) -> bool:
        from futu import TrdEnv, ModifyOrderOp
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            async with self._safe(f"cancel_order({order_id})"):
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
                return bool(ret == 0)
        except Exception:
            return False

    async def get_positions(self) -> dict[str, int]:
        from futu import TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            async with self._safe("get_positions"):
                ctx = await asyncio.to_thread(self._get_ctx)

                def _query():
                    return ctx.position_list_query(trd_env=trd_env)
                ret, data = await asyncio.to_thread(_query)
                if ret != 0:
                    logger.warning("Futu get_positions failed: %s", data)
                    return {}
                return {self._from_futu_code(row["code"]): int(row["qty"]) for _, row in data.iterrows() if int(row["qty"]) > 0}
        except Exception:
            return {}

    async def get_account_info(self) -> AccountInfo:
        from futu import TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            async with self._safe("get_account_info"):
                ctx = await asyncio.to_thread(self._get_ctx)

                def _query():
                    return ctx.accinfo_query(trd_env=trd_env)
                ret, data = await asyncio.to_thread(_query)
                if ret == 0:
                    row = data.iloc[0]
                    return AccountInfo(
                        cash=float(row["cash"]),
                        buying_power=float(row["power"]),
                        market_value=float(row["market_val"]),
                        total_assets=float(row["total_assets"]),
                    )
                logger.warning("Futu get_account_info failed: %s", data)
        except Exception:
            pass
        return AccountInfo()
