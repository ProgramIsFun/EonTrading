"""PriceMonitor: watches open positions, triggers SL/TP sells via [trade] channel.

Runs as a standalone component (own container in distributed mode).
Uses the same TradingLogic as backtest — identical SL/TP behavior.
"""
import asyncio
import logging

from src.common.clock import utcnow
from src.common.log_handler import ComponentFilter
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_TRADE, TradeEvent
from src.common.position_store import PositionStore
from src.common.price import get_price
from src.common.trading_logic import PositionState, TradingLogic

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("monitor"))


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
                qty = info.get("qty", 0)
                if price > 0:
                    self._states[sym] = PositionState(symbol=sym, shares=qty, entry_price=price)
            if self._states:
                logger.info("PriceMonitor restored %d position(s): %s", len(self._states), list(self._states.keys()))
        except Exception as e:
            logger.warning("PriceMonitor failed to restore entry prices: %s", e)
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

    def check_once_sync(self, as_of: str = None) -> list[str]:
        """Fast synchronous SL/TP check — for backtesting only. No async, no MongoDB, no broker calls."""
        from src.common.price import get_price
        if not self._states:
            return []
        sold = []
        for symbol in list(self._states.keys()):
            state = self._states[symbol]
            price = get_price(symbol, as_of=as_of)
            if price <= 0:
                continue
            self.logic.update_peak(state, price)
            sl = self.logic.check_stop_loss(state, price)
            if sl:
                logger.info("🛑 SL triggered: SELL %s %dsh @ $%.2f", symbol, state.shares, sl)
                self._states.pop(symbol)
                sold.append((symbol, sl, state.shares))
                continue
            tp = self.logic.check_take_profit(state, price)
            if tp:
                logger.info("🎯 TP triggered: SELL %s %dsh @ $%.2f", symbol, state.shares, tp)
                self._states.pop(symbol)
                sold.append((symbol, tp, state.shares))
        return sold

    def _ensure_entry_price(self, symbol: str):
        """Fetch entry price from store if not already known."""
        if symbol in self._states or not self.store:
            return
        try:
            positions = self.store.get_positions_with_prices()
            if symbol in positions:
                info = positions[symbol]
                price = info.get("entryPrice", 0.0)
                qty = info.get("qty", 0)
                if price > 0:
                    self._states[symbol] = PositionState(symbol=symbol, shares=qty, entry_price=price)
        except Exception:
            pass

    async def check_once(self, as_of: str = None) -> list[str]:
        """Check all positions against SL/TP. Returns list of symbols sold."""
        check_symbols = set(self._states.keys())
        all_positions: dict[str, dict] = {}
        if self.store:
            all_positions = self.store.get_positions_with_prices()
            check_symbols |= set(all_positions.keys())

        if not check_symbols:
            return []

        ts = as_of or (utcnow().isoformat() + "Z")
        sold = []
        for symbol in list(check_symbols):
            if symbol not in self._states:
                self._ensure_entry_price(symbol)
            if symbol not in self._states:
                continue  # no entry price — can't check SL/TP
            price = get_price(symbol, as_of=as_of)
            if price <= 0:
                continue

            info = all_positions.get(symbol, {})
            shares = info.get("qty", 1)
            state = self._get_or_create_state(symbol, price, shares)

            self.logic.update_peak(state, price)

            sl_price = self.logic.check_stop_loss(state, price)
            if sl_price:
                trade = TradeEvent(
                    symbol=symbol, action="sell",
                    reason=f"stop loss @ ${sl_price:.2f}",
                    timestamp=ts,
                    price=0.0, size=float(shares),
                )
                logger.info("🛑 SL triggered: SELL %s %dsh @ $%.2f", symbol, shares, sl_price)
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
                    price=0.0, size=float(shares),
                )
                logger.info("🎯 TP triggered: SELL %s %dsh @ $%.2f", symbol, shares, tp_price)
                await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
                self._states.pop(symbol, None)
                sold.append(symbol)

        # Clean up states for positions that no longer exist
        for sym in list(self._states.keys()):
            if sym not in check_symbols:
                del self._states[sym]

        return sold

    async def run(self):
        """Continuous monitoring loop for live mode."""
        logger.info("PriceMonitor started, checking every %ds", self.interval)
        while True:
            try:
                await self.check_once()
            except Exception as exc:
                logger.exception("PriceMonitor.check_once failed — %s", exc)
            await asyncio.sleep(self.interval)

    def register_entry(self, symbol: str, price: float, shares: int):
        """Called when a new position is opened — sets the entry price for SL/TP."""
        logger.info("📌 PriceMonitor: registered %s entry @ $%.2f (%dsh)", symbol, price, shares)
        self._states[symbol] = PositionState(symbol=symbol, shares=shares, entry_price=price)
