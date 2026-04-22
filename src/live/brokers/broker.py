"""Broker interface and Futu OpenD implementation."""
import asyncio
from abc import ABC, abstractmethod
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_TRADE, TradeEvent


class Broker(ABC):
    """Interface for trade execution."""

    @abstractmethod
    async def execute(self, trade: TradeEvent) -> bool:
        """Execute a trade. Returns True if successful."""
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


class LogBroker(Broker):
    """Dry-run broker that just logs trades. Good for testing."""

    async def execute(self, trade: TradeEvent) -> bool:
        print(f"  📝 [DRY RUN] {trade.action.upper()} {trade.symbol} | reason: {trade.reason}")
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
