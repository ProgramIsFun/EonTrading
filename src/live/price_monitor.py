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
from src.common.position_store import BasePositionStore
from src.common.price import get_price
from src.common.trading_logic import PositionState, TradingLogic

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("monitor"))


class PriceMonitor:
    """Polls prices for open positions, publishes sell trades when SL/TP hit."""

    def __init__(self, bus: EventBus, store: BasePositionStore, logic: TradingLogic,
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

    def _evaluate_positions(self, as_of: str = None) -> list[tuple]:
        """Core SL/TP evaluation — returns [(symbol, trigger_price, shares, reason), ...]."""
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
                sold.append((symbol, sl, state.shares, "stop loss"))
                continue
            tp = self.logic.check_take_profit(state, price)
            if tp:
                logger.info("🎯 TP triggered: SELL %s %dsh @ $%.2f", symbol, state.shares, tp)
                self._states.pop(symbol)
                sold.append((symbol, tp, state.shares, "take profit"))
        return sold

    def check_once_sync(self, as_of: str = None) -> list[tuple]:
        """Fast synchronous SL/TP check — for backtesting only. No async, no MongoDB, no broker calls."""
        return self._evaluate_positions(as_of)

    async def check_once(self, as_of: str = None) -> list[str]:
        """Check all positions against SL/TP. Publishes trade events, returns list of symbols sold."""
        all_positions: dict[str, dict] = {}
        if self.store:
            all_positions = self.store.get_positions_with_prices()
            for symbol, info in all_positions.items():
                if symbol not in self._states:
                    price = info.get("entryPrice", 0.0)
                    qty = info.get("qty", 0)
                    if price > 0:
                        self._states[symbol] = PositionState(symbol=symbol, shares=qty, entry_price=price)

        results = self._evaluate_positions(as_of)

        ts = as_of or (utcnow().isoformat() + "Z")
        sold = []
        for symbol, trigger_price, shares, reason in results:
            trade = TradeEvent(
                symbol=symbol, action="sell",
                reason=f"{reason} @ ${trigger_price:.2f}",
                timestamp=ts,
                price=0.0, size=float(shares),
            )
            await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
            sold.append(symbol)

        # Clean up states for positions that no longer exist
        check_symbols = set(all_positions.keys()) | set(self._states.keys())
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
