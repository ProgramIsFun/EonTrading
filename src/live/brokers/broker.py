"""Broker interface and implementations.

To add a new broker:
  1. Subclass Broker
  2. Implement execute() — submit order, return order_id
  3. Implement check_order() — OrderTracker polls this to confirm fills
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import uuid4

from src.common.clock import utcnow
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_TRADE, TradeEvent
from src.data.utils.db_helper import get_mongo_client
from src.settings import settings

logger = logging.getLogger(__name__)


class Broker(ABC):
    """Interface for trade execution.

    execute() submits the order and returns an order_id.
    OrderTracker polls check_order() to confirm fills or detect failures.
    """

    @abstractmethod
    async def execute(self, trade: TradeEvent) -> str | None:
        """Submit a trade. Returns order_id for tracking, or None on failure."""
        pass

    async def check_order(self, order_id: str) -> tuple[str, str | None]:
        """Returns (status, error_reason).
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
        return 0.0

    async def place_stop_loss(self, symbol: str, shares: int, stop_price: float) -> bool:
        return False

    async def place_take_profit(self, symbol: str, shares: int, target_price: float) -> bool:
        return False

    async def cancel_orders(self, symbol: str) -> bool:
        return False


# ---------------------------------------------------------------------------
# PaperBroker — dry run, instant fill
# ---------------------------------------------------------------------------
class PaperBroker(Broker):
    """Dry-run broker — fills instantly. Optionally applies transaction costs."""

    def __init__(self, initial_cash: float = 100000, cost_model=None):
        self._positions: dict[str, int] = {}
        self._cash = initial_cash
        self.cost_model = cost_model

    async def execute(self, trade: TradeEvent) -> str | None:
        qty = int(trade.size)
        if trade.action == "buy":
            cost = trade.price * qty
            fees = self.cost_model.buy_cost(trade.price, qty) if self.cost_model else 0
            total = cost + fees
            self._cash -= total
            self._positions[trade.symbol] = self._positions.get(trade.symbol, 0) + qty
            logger.info("📝 [DRY RUN] BUY %s %dsh @ $%.2f (fees: $%.2f) | %s", trade.symbol, qty, trade.price, fees, trade.reason)
        elif trade.action == "sell":
            qty = self._positions.pop(trade.symbol, 0)
            proceeds = trade.price * qty
            fees = self.cost_model.sell_cost(trade.price, qty) if self.cost_model else 0
            self._cash += proceeds - fees
            logger.info("📝 [DRY RUN] SELL %s %dsh @ $%.2f (fees: $%.2f) | %s", trade.symbol, qty, trade.price, fees, trade.reason)
        return f"paper-{trade.symbol}-{uuid4().hex[:8]}"

    async def check_order(self, order_id: str) -> tuple[str, str | None]:
        return ("filled", None)

    async def get_positions(self) -> dict[str, int]:
        return dict(self._positions)

    async def get_cash(self) -> float:
        return self._cash


# ---------------------------------------------------------------------------
# FutuBroker — HK/US market via Futu OpenD
#   confirm_mode="poll" (default): polls order status every N seconds
#   confirm_mode="callback": uses TradeOrderHandlerBase for real-time updates
# ---------------------------------------------------------------------------
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

    async def execute(self, trade: TradeEvent) -> str | None:
        from futu import TrdEnv, TrdSide
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        trd_side = TrdSide.BUY if trade.action == "buy" else TrdSide.SELL
        try:
            ctx = self._get_ctx()
            ret, data = ctx.place_order(
                price=trade.price, qty=int(trade.size),
                code=trade.symbol, trd_side=trd_side, trd_env=trd_env,
            )
            if ret != 0:
                logger.error("Futu order rejected: %s %s", trade.action.upper(), trade.symbol)
                return None
            order_id = str(data["order_id"].iloc[0])
            logger.info("📤 Futu order placed: %s %s (id=%s)", trade.action.upper(), trade.symbol, order_id)
            return order_id
        except Exception as e:
            logger.error("Futu order failed: %s — %s", trade.symbol, e)
            return None

    async def check_order(self, order_id: str) -> tuple[str, str | None]:
        from futu import OrderStatus, TrdEnv
        ctx = self._get_ctx()
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        ret, orders = ctx.order_list_query(order_id=int(order_id), trd_env=trd_env)
        if ret != 0:
            return "pending", None
        status = orders["order_status"].iloc[0]
        if status in (OrderStatus.FILLED_ALL, OrderStatus.FILLED_PART):
            return "filled", None
        if status in (OrderStatus.CANCELLED_ALL, OrderStatus.FAILED, OrderStatus.DELETED):
            return "cancelled", f"status: {status}"
        return "pending", None

    async def cancel_order(self, order_id: str) -> bool:
        from futu import TrdEnv
        ctx = self._get_ctx()
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        ret, _ = ctx.undo_order(order_id=int(order_id), trd_env=trd_env)
        return ret == 0

    async def get_positions(self) -> dict[str, int]:
        from futu import TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            ctx = self._get_ctx()
            ret, data = ctx.position_list_query(trd_env=trd_env)
            if ret != 0:
                return {}
            return {row["code"]: int(row["qty"]) for _, row in data.iterrows() if int(row["qty"]) > 0}
        except Exception as e:
            logger.error("Futu get_positions error: %s", e)
            return {}

    async def get_cash(self) -> float:
        from futu import TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            ctx = self._get_ctx()
            ret, data = ctx.accinfo_query(trd_env=trd_env)
            if ret == 0:
                return float(data["cash"].iloc[0])
        except Exception as e:
            logger.error("Futu get_cash error: %s", e)
        return 0.0


# ---------------------------------------------------------------------------
# IBKRBroker — Interactive Brokers via ib_insync, confirms via callback
# ---------------------------------------------------------------------------
class IBKRBroker(Broker):
    """pip install ib_insync

    Connects to TWS or IB Gateway. Confirmation via orderStatusEvent callback.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib = None

    def _connect(self):
        if self._ib and self._ib.isConnected():
            return
        from ib_insync import IB
        self._ib = IB()
        self._ib.connect(self.host, self.port, clientId=self.client_id)

    async def execute(self, trade: TradeEvent) -> str | None:
        from ib_insync import MarketOrder, Stock
        try:
            self._connect()
            contract = Stock(trade.symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)
            action = "BUY" if trade.action == "buy" else "SELL"
            order = MarketOrder(action, int(trade.size))
            ib_trade = self._ib.placeOrder(contract, order)

            # Wait for fill confirmation
            import asyncio
            while not ib_trade.isDone():
                await asyncio.sleep(0.5)
                self._ib.sleep(0)

            order_id = str(ib_trade.order.orderId)
            return order_id
        except Exception as e:
            logger.error("IBKR order failed: %s — %s", trade.symbol, e)
            return None

    async def check_order(self, order_id: str) -> tuple[str, str | None]:
        from ib_insync import Order
        try:
            self._connect()
            trades = self._ib.trades()
            for t in trades:
                if str(t.order.orderId) == order_id:
                    status = t.orderStatus.status
                    if status == "Filled":
                        return ("filled", None)
                    if status in ("Cancelled", "Inactive", "ApiCancelled"):
                        return ("cancelled", status)
                    return ("pending", None)
            return ("pending", None)
        except Exception as e:
            logger.error("IBKR check_order error: %s", e)
            return ("pending", None)

    async def get_positions(self) -> dict[str, int]:
        try:
            self._connect()
            return {p.contract.symbol: int(p.position) for p in self._ib.positions() if p.position > 0}
        except Exception as e:
            logger.error("IBKR get_positions error: %s", e)
            return {}

    async def get_cash(self) -> float:
        try:
            self._connect()
            for av in self._ib.accountValues():
                if av.tag == "CashBalance" and av.currency == "USD":
                    return float(av.value)
        except Exception as e:
            logger.error("IBKR get_cash error: %s", e)
        return 0.0


# ---------------------------------------------------------------------------
# AlpacaBroker — Alpaca Markets (US), confirms by polling order status
# ---------------------------------------------------------------------------
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

    async def check_order(self, order_id: str) -> tuple[str, str | None]:
        try:
            self._connect()
            order = self._api.get_order(order_id)
            if order.status == "filled":
                return ("filled", None)
            if order.status in ("canceled", "expired", "rejected"):
                return ("cancelled", order.status)
            return ("pending", None)
        except Exception as e:
            logger.error("Alpaca check_order error: %s", e)
            return ("pending", None)

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


# ---------------------------------------------------------------------------
# TradeExecutor — routes [trade] events to the configured broker
# ---------------------------------------------------------------------------
class TradeExecutor:
    """Listens to trade events, submits orders via broker, writes to orders collection.

    Does NOT track fill results — OrderTracker handles confirmation via polling.
    """

    def __init__(self, bus: EventBus, broker: Broker):
        self.bus = bus
        self.broker = broker
        self._seen: set[str] = set()

    async def start(self):
        await self.bus.subscribe(CHANNEL_TRADE, self._on_trade)

    async def _on_trade(self, msg: dict):
        trade = TradeEvent.from_dict(msg)
        dedup_key = f"{trade.symbol}:{trade.action}:{trade.timestamp}"
        if dedup_key in self._seen:
            logger.warning("Duplicate trade ignored: %s %s @ %s", trade.action, trade.symbol, trade.timestamp)
            return
        self._seen.add(dedup_key)
        if len(self._seen) > 10000:
            self._seen = set(list(self._seen)[-5000:])

        order_id = await self.broker.execute(trade)
        if order_id is None:
            logger.error("Order submission failed: %s %s", trade.action.upper(), trade.symbol)
            return
        col = get_mongo_client()["EonTradingDB"]["orders"]
        doc = {
            "order_id": order_id,
            "broker_type": self.broker.__class__.__name__,
            "symbol": trade.symbol,
            "action": trade.action,
            "price": trade.price,
            "shares": trade.size,
            "reason": trade.reason,
            "timestamp": trade.timestamp,
            "status": "pending",
            "placed_at": utcnow(),
            "checked_at": None,
            "filled_at": None,
            "cancelled_at": None,
            "next_check_at": utcnow(),
            "retry_count": 0,
            "error": None,
        }
        await asyncio.to_thread(col.insert_one, doc)
