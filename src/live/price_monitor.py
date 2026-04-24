"""PriceMonitor: watches open positions, triggers SL/TP sells via [trade] channel.

Runs as a standalone component (own container in distributed mode).
Uses the same TradingLogic as backtest — identical SL/TP behavior.
"""
import asyncio
from datetime import datetime
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_TRADE, TradeEvent
from src.common.price import get_price
from src.common.position_store import PositionStore
from src.common.trading_logic import TradingLogic, PositionState


class PriceMonitor:
    """Polls prices for open positions, publishes sell trades when SL/TP hit."""

    def __init__(self, bus: EventBus, store: PositionStore, logic: TradingLogic,
                 interval_sec: int = 60, entry_prices: dict = None):
        self.bus = bus
        self.store = store
        self.logic = logic
        self.interval = interval_sec
        self._states: dict[str, PositionState] = {}
        # Restore entry prices from store on startup
        try:
            for sym, info in store.get_positions_with_prices().items():
                price = info.get("entryPrice", 0.0)
                if price > 0:
                    self._states[sym] = PositionState(symbol=sym, shares=0, entry_price=price)
            if self._states:
                print(f"  PriceMonitor restored {len(self._states)} entry price(s): {list(self._states.keys())}")
        except Exception:
            pass
        # Allow injecting known entry prices (for testing)
        if entry_prices:
            for sym, price in entry_prices.items():
                self._states[sym] = PositionState(symbol=sym, shares=0, entry_price=price)

    def _get_or_create_state(self, symbol: str, price: float, shares: int) -> PositionState:
        if symbol not in self._states:
            self._states[symbol] = PositionState(symbol=symbol, shares=shares, entry_price=price)
        state = self._states[symbol]
        state.shares = shares
        return state

    async def check_once(self, broker=None, as_of: str = None) -> list[str]:
        """Check all positions against SL/TP. Returns list of symbols sold."""
        positions = self.store.get_positions()
        broker_positions = {}
        if broker:
            broker_positions = await broker.get_positions()

        if not positions and not self._states:
            return []

        ts = as_of or (datetime.utcnow().isoformat() + "Z")
        sold = []
        # Check all symbols that have entry prices registered
        check_symbols = set(positions.keys()) | set(self._states.keys())
        for symbol in list(check_symbols):
            if symbol not in self._states:
                continue  # no entry price — can't check SL/TP
            price = get_price(symbol, as_of=as_of)
            if price <= 0:
                continue

            shares = broker_positions.get(symbol, 1)
            state = self._get_or_create_state(symbol, price, shares)

            self.logic.update_peak(state, price)

            sl_price = self.logic.check_stop_loss(state, price)
            if sl_price:
                trade = TradeEvent(
                    symbol=symbol, action="sell",
                    reason=f"stop loss @ ${sl_price:.2f}",
                    timestamp=ts,
                    price=sl_price, size=float(shares),
                )
                print(f"  🛑 SL triggered: SELL {symbol} {shares}sh @ ${sl_price:.2f}")
                await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
                self._states.pop(symbol, None)
                sold.append(symbol)
                continue

            tp_price = self.logic.check_take_profit(state, price)
            if tp_price:
                trade = TradeEvent(
                    symbol=symbol, action="sell",
                    reason=f"take profit @ ${tp_price:.2f}",
                    timestamp=ts,
                    price=tp_price, size=float(shares),
                )
                print(f"  🎯 TP triggered: SELL {symbol} {shares}sh @ ${tp_price:.2f}")
                await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
                self._states.pop(symbol, None)
                sold.append(symbol)

        # Clean up states for positions that no longer exist
        active = set(positions.keys()) | set(broker_positions.keys())
        for sym in list(self._states.keys()):
            if sym not in active:
                del self._states[sym]

        return sold

    async def run(self, broker=None):
        """Continuous monitoring loop for live mode."""
        print(f"  PriceMonitor started, checking every {self.interval}s")
        while True:
            await self.check_once(broker)
            await asyncio.sleep(self.interval)

    def register_entry(self, symbol: str, price: float, shares: int):
        """Called when a new position is opened — sets the entry price for SL/TP."""
        print(f"    📌 PriceMonitor: registered {symbol} entry @ ${price:.2f} ({shares}sh)")
        self._states[symbol] = PositionState(symbol=symbol, shares=shares, entry_price=price)
