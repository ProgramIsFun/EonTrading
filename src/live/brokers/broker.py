"""Broker interface and implementations.

To add a new broker:
  1. Subclass Broker
  2. Implement execute() — submit order, then call self._publish_fill() when confirmed
  3. Each broker handles confirmation differently:
     - LogBroker: instant (dry run)
     - FutuBroker: polls order status
     - IBKRBroker: callback via ib_insync
     - AlpacaBroker: REST polling or websocket
"""
from abc import ABC, abstractmethod
from datetime import datetime
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_TRADE, CHANNEL_FILL, TradeEvent, FillEvent


class Broker(ABC):
    """Interface for trade execution.

    Brokers publish FillEvent to [fill] channel when the order is confirmed or rejected.
    Confirmation mechanism varies by broker (polling, callback, websocket, instant).
    """

    def set_bus(self, bus: EventBus):
        self._bus = bus

    async def _publish_fill(self, symbol: str, action: str, success: bool, reason: str = ""):
        fill = FillEvent(
            symbol=symbol, action=action, success=success,
            reason=reason or ("filled" if success else "broker rejected"),
            timestamp=datetime.utcnow().isoformat() + "Z",
        )
        await self._bus.publish(CHANNEL_FILL, fill.to_dict())

    @abstractmethod
    async def execute(self, trade: TradeEvent):
        """Submit a trade. Must eventually call _publish_fill()."""
        pass

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
# LogBroker — dry run, instant fill
# ---------------------------------------------------------------------------
class LogBroker(Broker):
    """Dry-run broker — fills instantly."""

    def __init__(self, initial_cash: float = 100000):
        self._positions: dict[str, int] = {}
        self._cash = initial_cash

    async def execute(self, trade: TradeEvent):
        print(f"  📝 [DRY RUN] {trade.action.upper()} {trade.symbol} qty={int(trade.size)} @ ${trade.price:.2f} | reason: {trade.reason}")
        if trade.action == "buy":
            cost = trade.price * trade.size
            self._cash -= cost
            self._positions[trade.symbol] = self._positions.get(trade.symbol, 0) + int(trade.size)
        elif trade.action == "sell":
            qty = self._positions.pop(trade.symbol, 0)
            self._cash += trade.price * qty
        await self._publish_fill(trade.symbol, trade.action, True, "filled (dry run)")

    async def get_positions(self) -> dict[str, int]:
        return dict(self._positions)

    async def get_cash(self) -> float:
        return self._cash


# ---------------------------------------------------------------------------
# FutuBroker — HK/US market via Futu OpenD, confirms by polling order status
# ---------------------------------------------------------------------------
class FutuBroker(Broker):
    """pip install futu-api"""

    def __init__(self, host: str = "127.0.0.1", port: int = 11111, simulate: bool = True,
                 poll_interval: float = 2.0, poll_timeout: float = 60.0):
        self.host = host
        self.port = port
        self.simulate = simulate
        self.poll_interval = poll_interval
        self.poll_timeout = poll_timeout

    async def execute(self, trade: TradeEvent):
        import asyncio
        from futu import OpenSecTradeContext, TrdSide, TrdEnv, OrderStatus
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        trd_side = TrdSide.BUY if trade.action == "buy" else TrdSide.SELL
        try:
            ctx = OpenSecTradeContext(host=self.host, port=self.port)
            ret, data = ctx.place_order(
                price=trade.price, qty=int(trade.size * 100),
                code=trade.symbol, trd_side=trd_side, trd_env=trd_env,
            )
            if ret != 0:
                ctx.close()
                await self._publish_fill(trade.symbol, trade.action, False, "order rejected")
                return

            order_id = data["order_id"].iloc[0]
            print(f"  📤 Futu order placed: {trade.action.upper()} {trade.symbol} (polling...)")

            elapsed = 0.0
            while elapsed < self.poll_timeout:
                await asyncio.sleep(self.poll_interval)
                elapsed += self.poll_interval
                ret2, orders = ctx.order_list_query(order_id=order_id, trd_env=trd_env)
                if ret2 != 0:
                    continue
                status = orders["order_status"].iloc[0]
                if status in (OrderStatus.FILLED_ALL, OrderStatus.FILLED_PART):
                    ctx.close()
                    await self._publish_fill(trade.symbol, trade.action, True)
                    return
                if status in (OrderStatus.CANCELLED_ALL, OrderStatus.FAILED, OrderStatus.DELETED):
                    ctx.close()
                    await self._publish_fill(trade.symbol, trade.action, False, f"status: {status}")
                    return

            ctx.close()
            await self._publish_fill(trade.symbol, trade.action, False, "timeout")
        except Exception as e:
            await self._publish_fill(trade.symbol, trade.action, False, str(e))

    async def get_positions(self) -> dict[str, int]:
        from futu import OpenSecTradeContext, TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            ctx = OpenSecTradeContext(host=self.host, port=self.port)
            ret, data = ctx.position_list_query(trd_env=trd_env)
            ctx.close()
            if ret != 0:
                return {}
            return {row["code"]: int(row["qty"]) for _, row in data.iterrows() if int(row["qty"]) > 0}
        except Exception as e:
            print(f"  ❌ Futu get_positions error: {e}")
            return {}

    async def get_cash(self) -> float:
        from futu import OpenSecTradeContext, TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            ctx = OpenSecTradeContext(host=self.host, port=self.port)
            ret, data = ctx.accinfo_query(trd_env=trd_env)
            ctx.close()
            if ret == 0:
                return float(data["cash"].iloc[0])
        except Exception as e:
            print(f"  ❌ Futu get_cash error: {e}")
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

    async def execute(self, trade: TradeEvent):
        import asyncio
        from ib_insync import Stock, MarketOrder
        try:
            self._connect()
            contract = Stock(trade.symbol, "SMART", "USD")
            self._ib.qualifyContracts(contract)
            action = "BUY" if trade.action == "buy" else "SELL"
            order = MarketOrder(action, int(trade.size))
            ib_trade = self._ib.placeOrder(contract, order)

            # Wait for fill via callback
            while not ib_trade.isDone():
                await asyncio.sleep(0.5)
                self._ib.sleep(0)

            filled = ib_trade.orderStatus.status == "Filled"
            await self._publish_fill(trade.symbol, trade.action, filled,
                                     "filled" if filled else ib_trade.orderStatus.status)
        except Exception as e:
            await self._publish_fill(trade.symbol, trade.action, False, str(e))

    async def get_positions(self) -> dict[str, int]:
        try:
            self._connect()
            return {p.contract.symbol: int(p.position) for p in self._ib.positions() if p.position > 0}
        except Exception as e:
            print(f"  ❌ IBKR get_positions error: {e}")
            return {}

    async def get_cash(self) -> float:
        try:
            self._connect()
            for av in self._ib.accountValues():
                if av.tag == "CashBalance" and av.currency == "USD":
                    return float(av.value)
        except Exception as e:
            print(f"  ❌ IBKR get_cash error: {e}")
        return 0.0


# ---------------------------------------------------------------------------
# AlpacaBroker — Alpaca Markets (US), confirms by polling order status
# ---------------------------------------------------------------------------
class AlpacaBroker(Broker):
    """pip install alpaca-trade-api

    Uses Alpaca paper or live trading API.
    """

    def __init__(self, api_key: str = "", secret_key: str = "", paper: bool = True):
        import os
        self.api_key = api_key or os.getenv("ALPACA_API_KEY", "")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")
        self.base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        self._api = None

    def _connect(self):
        if self._api:
            return
        import alpaca_trade_api as tradeapi
        self._api = tradeapi.REST(self.api_key, self.secret_key, self.base_url, api_version="v2")

    async def execute(self, trade: TradeEvent):
        import asyncio
        try:
            self._connect()
            order = self._api.submit_order(
                symbol=trade.symbol, qty=int(trade.size),
                side=trade.action, type="market", time_in_force="day",
            )
            # Poll until terminal state
            for _ in range(30):
                await asyncio.sleep(2)
                order = self._api.get_order(order.id)
                if order.status == "filled":
                    await self._publish_fill(trade.symbol, trade.action, True)
                    return
                if order.status in ("canceled", "expired", "rejected"):
                    await self._publish_fill(trade.symbol, trade.action, False, order.status)
                    return

            await self._publish_fill(trade.symbol, trade.action, False, "timeout")
        except Exception as e:
            await self._publish_fill(trade.symbol, trade.action, False, str(e))

    async def get_positions(self) -> dict[str, int]:
        try:
            self._connect()
            return {p.symbol: int(p.qty) for p in self._api.list_positions()}
        except Exception as e:
            print(f"  ❌ Alpaca get_positions error: {e}")
            return {}

    async def get_cash(self) -> float:
        try:
            self._connect()
            return float(self._api.get_account().cash)
        except Exception as e:
            print(f"  ❌ Alpaca get_cash error: {e}")
        return 0.0


# ---------------------------------------------------------------------------
# TradeExecutor — routes [trade] events to the configured broker
# ---------------------------------------------------------------------------
class TradeExecutor:
    """Listens to trade events and forwards to broker. Broker publishes fill results.

    Safety: in replay mode (clock.is_replay), real brokers are blocked.
    Only LogBroker is allowed during backtest replay.
    """

    def __init__(self, bus: EventBus, broker: Broker):
        self.bus = bus
        self.broker = broker
        self.broker.set_bus(bus)

    async def start(self):
        await self.bus.subscribe(CHANNEL_TRADE, self._on_trade)

    async def _on_trade(self, msg: dict):
        trade = TradeEvent.from_dict(msg)
        await self.broker.execute(trade)
