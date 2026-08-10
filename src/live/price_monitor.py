"""PriceMonitor: watches open positions, triggers SL/TP sells and executes them.

The monitor owns its exits end-to-end: it decides a stop-loss/take-profit
sell via TradingLogic and executes it directly through the broker, then
publishes the [trade] event so the position store / OrderTracker learn the
position closed.  Decision and execution live together (like the trader);
the bus stays the observability + state-sync channel.
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
from src.live.brokers.broker import Broker
from src.live.order_logger import noop_log_order

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("monitor"))


class PriceMonitor:
    """Polls prices for open positions, executes sell trades when SL/TP hit."""

    def __init__(self, bus: EventBus, store: BasePositionStore, logic: TradingLogic,
                 interval_sec: int = 60, entry_prices: dict | None = None,
                 broker: Broker | None = None, log_order=None):
        self.bus = bus
        self.store = store
        self.logic = logic
        self.interval = interval_sec
        self.broker = broker
        self._log_order = log_order or noop_log_order
        self._states: dict[str, PositionState] = {}
        # Restore entry prices + peak from store on startup
        try:
            for sym, info in store.get_positions_with_prices().items():
                price = info.get("entryPrice", 0.0)
                qty = info.get("qty", 0)
                peak = info.get("peakPrice", price)
                if price > 0:
                    self._states[sym] = PositionState(symbol=sym, shares=qty,
                                                      entry_price=price, peak_price=peak)
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

    def _evaluate_positions(self, as_of: str | None = None) -> list[tuple]:
        """Core SL/TP evaluation — returns [(symbol, trigger_price, shares, reason), ...].

        Does NOT mutate state: triggers are returned so the caller decides
        when to pop the position (after a successful fill).
        """
        if not self._states:
            return []
        sold = []
        for symbol in list(self._states.keys()):
            state = self._states[symbol]
            price = get_price(symbol, as_of=as_of)
            if price <= 0:
                continue
            old_peak = state.peak_price
            self.logic.update_peak(state, price)
            if self.logic.trailing_sl and state.peak_price > old_peak:
                try:
                    self.store.update_peak(symbol, state.peak_price)
                except Exception as e:
                    logger.warning("Failed to persist peak for %s: %s", symbol, e)
            sl = self.logic.check_stop_loss(state, price)
            if sl:
                logger.info("🛑 SL triggered: SELL %s %dsh @ $%.2f", symbol, state.shares, sl)
                sold.append((symbol, sl, state.shares, "stop loss"))
                continue
            tp = self.logic.check_take_profit(state, price)
            if tp:
                logger.info("🎯 TP triggered: SELL %s %dsh @ $%.2f", symbol, state.shares, tp)
                sold.append((symbol, tp, state.shares, "take profit"))
        return sold

    def check_once_sync(self, as_of: str | None = None) -> list[tuple]:
        """Fast synchronous SL/TP check — for backtesting only. No async, no MongoDB, no broker calls."""
        results = self._evaluate_positions(as_of)
        for symbol, _price, _shares, _reason in results:
            self._states.pop(symbol, None)
        return results

    async def check_once(self, as_of: str | None = None) -> list[str]:
        """Check all positions against SL/TP. Executes sells, publishes [trade] events.

        A position is popped from monitoring state only after a successful
        broker fill, so a failed execution is retried on the next tick instead
        of silently abandoning the stop-loss.  Returns symbols sold.
        """
        all_positions: dict[str, dict] = {}
        if self.store:
            all_positions = self.store.get_positions_with_prices()
            for symbol, info in all_positions.items():
                if symbol not in self._states:
                    price = info.get("entryPrice", 0.0)
                    qty = info.get("qty", 0)
                    peak = info.get("peakPrice", price)
                    if price > 0:
                        self._states[symbol] = PositionState(symbol=symbol, shares=qty,
                                                              entry_price=price, peak_price=peak)
                else:
                    # Update shares from store (position may have changed via averaging)
                    self._states[symbol].shares = info.get("qty", self._states[symbol].shares)

        results = self._evaluate_positions(as_of)

        ts = as_of or (utcnow().isoformat() + "Z")
        sold = []
        for symbol, trigger_price, shares, reason in results:
            price = await asyncio.to_thread(get_price, symbol, ts)
            if price <= 0:
                logger.warning("No price for %s — keeping stop-loss state, will retry", symbol)
                continue
            trade = TradeEvent(
                symbol=symbol, action="sell",
                reason=f"{reason} @ ${trigger_price:.2f}",
                timestamp=ts,
                price=price, size=float(shares),
            )
            filled = await self._execute(trade)
            if not filled:
                logger.warning("SL/TP sell failed for %s — position stays monitored", symbol)
                continue
            self._states.pop(symbol, None)
            await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
            sold.append(symbol)

        # Clean up states for positions that no longer exist
        check_symbols = set(all_positions.keys()) | set(self._states.keys())
        for sym in list(self._states.keys()):
            if sym not in check_symbols:
                del self._states[sym]

        return sold

    async def _execute(self, trade: TradeEvent) -> bool:
        """Execute a sell via the broker and log the order. Returns True on fill."""
        if self.broker is None:
            logger.warning("PriceMonitor has no broker — cannot execute %s %s",
                           trade.action.upper(), trade.symbol)
            return False
        try:
            order_id = await self.broker.execute(trade)
            broker_name = self.broker.__class__.__name__
            if order_id:
                await self._log_order(trade, order_id, broker_name)
                logger.info("Filled: SELL %s (order_id=%s)", trade.symbol, order_id)
                return True
            await self._log_order(trade, None, broker_name, status="failed",
                                  error="broker returned None")
            logger.warning("Order failed: SELL %s", trade.symbol)
            return False
        except Exception:
            logger.error("Broker execution failed: SELL %s", trade.symbol, exc_info=True)
            return False

    async def run(self):
        """Continuous monitoring loop for live mode."""
        logger.info("PriceMonitor started, checking every %ds", self.interval)
        check_count = 0
        while True:
            try:
                await self.check_once()
                check_count += 1
                if check_count % 5 == 0 and self._states:
                    symbols = list(self._states.keys())
                    logger.info("Monitoring %d position(s): %s", len(symbols), ", ".join(symbols))
            except Exception as exc:
                logger.exception("PriceMonitor.check_once failed — %s", exc)
            await asyncio.sleep(self.interval)

    def register_entry(self, symbol: str, price: float, shares: int):
        """Called when a new position is opened — sets the entry price for SL/TP."""
        logger.info("📌 PriceMonitor: registered %s entry @ $%.2f (%dsh)", symbol, price, shares)
        self._states[symbol] = PositionState(symbol=symbol, shares=shares, entry_price=price)
