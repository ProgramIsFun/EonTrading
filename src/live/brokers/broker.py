"""Broker interface and implementations."""
from abc import ABC, abstractmethod
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_TRADE, TradeEvent


class Broker(ABC):
    """Interface for trade execution and position queries."""

    @abstractmethod
    async def execute(self, trade: TradeEvent) -> bool:
        """Execute a trade. Returns True if successful."""
        pass

    @abstractmethod
    async def get_positions(self) -> dict[str, int]:
        """Returns current positions as {symbol: shares}."""
        pass

    @abstractmethod
    async def place_stop_loss(self, symbol: str, shares: int, stop_price: float) -> bool:
        """Place a stop-loss order. Broker monitors and executes when price hits stop_price."""
        pass

    @abstractmethod
    async def place_take_profit(self, symbol: str, shares: int, target_price: float) -> bool:
        """Place a take-profit order. Broker monitors and executes when price hits target_price."""
        pass

    @abstractmethod
    async def cancel_orders(self, symbol: str) -> bool:
        """Cancel all pending SL/TP orders for a symbol (e.g. when selling manually)."""
        pass


class FutuBroker(Broker):
    """Execute trades via Futu OpenD (HK market)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 11111, simulate: bool = True):
        self.host = host
        self.port = port
        self.simulate = simulate

    async def execute(self, trade: TradeEvent) -> bool:
        from futu import OpenSecTradeContext, TrdSide, TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        trd_side = TrdSide.BUY if trade.action == "buy" else TrdSide.SELL
        try:
            ctx = OpenSecTradeContext(host=self.host, port=self.port)
            ret, data = ctx.place_order(
                price=trade.price, qty=int(trade.size * 100),
                code=trade.symbol, trd_side=trd_side, trd_env=trd_env,
            )
            ctx.close()
            ok = ret == 0
            status = "✅" if ok else "❌"
            print(f"  {status} Futu {trade.action.upper()} {trade.symbol} ({'sim' if self.simulate else 'real'})")
            return ok
        except Exception as e:
            print(f"  ❌ Futu error: {e}")
            return False

    async def get_positions(self) -> dict[str, int]:
        from futu import OpenSecTradeContext, TrdEnv
        trd_env = TrdEnv.SIMULATE if self.simulate else TrdEnv.REAL
        try:
            ctx = OpenSecTradeContext(host=self.host, port=self.port)
            ret, data = ctx.position_list_query(trd_env=trd_env)
            ctx.close()
            if ret != 0:
                return {}
            positions = {}
            for _, row in data.iterrows():
                sym = row["code"]
                qty = int(row["qty"])
                if qty > 0:
                    positions[sym] = qty
            return positions
        except Exception as e:
            print(f"  ❌ Futu get_positions error: {e}")
            return {}

    async def place_stop_loss(self, symbol: str, shares: int, stop_price: float) -> bool:
        # TODO: Implement via Futu's conditional order API
        print(f"  📋 Futu SL order: {symbol} {shares}sh @ ${stop_price:.2f}")
        return True

    async def place_take_profit(self, symbol: str, shares: int, target_price: float) -> bool:
        # TODO: Implement via Futu's conditional order API
        print(f"  📋 Futu TP order: {symbol} {shares}sh @ ${target_price:.2f}")
        return True

    async def cancel_orders(self, symbol: str) -> bool:
        # TODO: Implement via Futu's order cancellation API
        print(f"  📋 Futu cancel orders: {symbol}")
        return True


class LogBroker(Broker):
    """Dry-run broker that tracks positions in memory."""

    def __init__(self):
        self._positions: dict[str, int] = {}
        self._orders: dict[str, list] = {}  # symbol → [{"type": "sl"/"tp", "price": ...}]

    async def execute(self, trade: TradeEvent) -> bool:
        print(f"  📝 [DRY RUN] {trade.action.upper()} {trade.symbol} | reason: {trade.reason}")
        if trade.action == "buy":
            self._positions[trade.symbol] = self._positions.get(trade.symbol, 0) + int(trade.size)
        elif trade.action == "sell":
            self._positions.pop(trade.symbol, None)
            self._orders.pop(trade.symbol, None)  # cancel pending orders on sell
        return True

    async def get_positions(self) -> dict[str, int]:
        return dict(self._positions)

    async def place_stop_loss(self, symbol: str, shares: int, stop_price: float) -> bool:
        self._orders.setdefault(symbol, []).append({"type": "sl", "shares": shares, "price": stop_price})
        print(f"  📝 [DRY RUN] SL order: {symbol} {shares}sh @ ${stop_price:.2f}")
        return True

    async def place_take_profit(self, symbol: str, shares: int, target_price: float) -> bool:
        self._orders.setdefault(symbol, []).append({"type": "tp", "shares": shares, "price": target_price})
        print(f"  📝 [DRY RUN] TP order: {symbol} {shares}sh @ ${target_price:.2f}")
        return True

    async def cancel_orders(self, symbol: str) -> bool:
        removed = len(self._orders.pop(symbol, []))
        if removed:
            print(f"  📝 [DRY RUN] Cancelled {removed} orders for {symbol}")
        return True


class TradeExecutor:
    """Listens to trade events and executes via broker."""

    def __init__(self, bus: EventBus, broker: Broker):
        self.bus = bus
        self.broker = broker

    async def start(self):
        await self.bus.subscribe(CHANNEL_TRADE, self._on_trade)

    async def _on_trade(self, msg: dict):
        trade = TradeEvent.from_dict(msg)
        await self.broker.execute(trade)
