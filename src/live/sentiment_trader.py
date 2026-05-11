"""SentimentTrader: listens to sentiment events, decides trades, publishes trade events."""
import asyncio
import logging
from datetime import datetime

from src.common.clock import utcnow
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_FILL, CHANNEL_SENTIMENT, CHANNEL_TRADE, FillEvent, SentimentEvent, TradeEvent
from src.common.price import get_price
from src.common.trade_store import trade_to_doc
from src.common.trading_logic import TradingLogic

logger = logging.getLogger(__name__)


class SentimentTrader:
    """Listens to sentiment events and decides trades.

    Flow: decide → mark pending → publish trade → wait for fill → confirm or rollback.
    Timestamps flow with events — no global clock needed.
    """

    def __init__(self, bus: EventBus, logic: TradingLogic = None, max_hold_days: int = 0,
                 position_store=None, trade_log=None, broker=None, price_monitor=None, **kwargs):
        self.bus = bus
        self.logic = logic or TradingLogic(**kwargs)
        self.holdings: dict[str, datetime] = {}
        self.pending: dict[str, dict] = {}  # symbol → {"action", "price", "shares"}
        self.max_hold_days = max_hold_days
        self.position_store = position_store
        self._trades_col = trade_log
        self.broker = broker
        self.price_monitor = price_monitor
        if self.position_store:
            self.holdings = self.position_store.get_positions()
            if self.holdings:
                logger.info("Restored %d position(s) from store: %s", len(self.holdings), list(self.holdings.keys()))

    async def start(self):
        await self.bus.subscribe(CHANNEL_SENTIMENT, self._on_sentiment)
        await self.bus.subscribe(CHANNEL_FILL, self._on_fill)
        if self.max_hold_days > 0:
            self._hold_task = asyncio.create_task(self._hold_checker())

    async def _on_fill(self, msg: dict):
        event = FillEvent.from_dict(msg)
        symbol = event.symbol
        pending = self.pending.pop(symbol, None)
        if not pending:
            return

        action = pending["action"]
        entry_price = pending.get("price", 0.0)
        shares = pending.get("shares", 1)

        if event.success:
            logger.info("✅ %s %s confirmed by broker", action.upper(), symbol)
            if self._trades_col is not None:
                doc = trade_to_doc(symbol, action, entry_price, shares, event.reason, event.timestamp)
                await asyncio.to_thread(self._trades_col.insert_one, doc)
            if self.position_store:
                if action == "buy":
                    await asyncio.to_thread(
                        self.position_store.open_position, symbol, self.holdings[symbol], entry_price)
                    if self.price_monitor:
                        self.price_monitor.register_entry(symbol, entry_price, shares)
                elif action == "sell":
                    await asyncio.to_thread(self.position_store.close_position, symbol)
        else:
            logger.warning("⚠️ %s %s rejected by broker: %s", action.upper(), symbol, event.reason)
            if action == "buy":
                self.holdings.pop(symbol, None)
            elif action == "sell":
                self.holdings[symbol] = utcnow()

    async def _hold_checker(self):
        while True:
            now = utcnow()
            for symbol in list(self.holdings.keys()):
                if symbol in self.pending:
                    continue
                entry_time = self.holdings[symbol]
                held_days = (now - entry_time).total_seconds() / 86400
                if held_days >= self.max_hold_days:
                    del self.holdings[symbol]
                    self.pending[symbol] = {"action": "sell", "price": 0, "shares": 0}
                    trade = TradeEvent(
                        symbol=symbol, action="sell",
                        reason=f"max hold {self.max_hold_days}d reached",
                        timestamp=now.isoformat() + "Z",
                    )
                    logger.info("SELL %s (max hold %dd reached) — pending broker confirmation", symbol, self.max_hold_days)
                    await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
            await asyncio.sleep(3600)

    async def _on_sentiment(self, msg: dict):
        event = SentimentEvent.from_dict(msg)
        if not event.symbols:
            return

        event_ts = event.timestamp

        for symbol in event.symbols:
            if symbol in self.pending:
                continue

            action = None
            shares = 0
            price = 0.0

            if self.logic.should_sell_on_sentiment(event.sentiment, event.confidence, symbol, self.holdings):
                action = "sell"
                if self.broker:
                    broker_positions = await self.broker.get_positions()
                    shares = broker_positions.get(symbol, 1)
                else:
                    shares = 1
                # to_thread: get_price uses synchronous requests (yfinance), would block the event loop
                price = await asyncio.to_thread(get_price, symbol, event_ts)
                self.holdings.pop(symbol, None)
            elif symbol not in self.holdings:
                if event.confidence < self.logic.min_confidence or event.sentiment < self.logic.threshold:
                    continue
                # to_thread: get_price uses synchronous requests (yfinance), would block the event loop
                price = await asyncio.to_thread(get_price, symbol, event_ts)
                if price <= 0:
                    continue
                cash = await self.broker.get_cash() if self.broker else 0.0
                if cash > 0:
                    shares = self.logic.should_buy(
                        event.sentiment, event.confidence, symbol,
                        self.holdings, cash, price,
                    )
                else:
                    # No broker or no cash info — buy 1 share as fallback
                    shares = 1
                if shares > 0:
                    action = "buy"
                    self.holdings[symbol] = utcnow()

            if action:
                self.pending[symbol] = {"action": action, "price": price, "shares": shares}
                trade = TradeEvent(
                    symbol=symbol, action=action,
                    reason=f"sentiment:{event.sentiment:.2f} on {event.headline[:60]}",
                    timestamp=event_ts,
                    price=price,
                    size=float(shares) if shares else 1.0,
                )
                logger.info("%s %s qty=%d @ $%.2f (sentiment: %.2f) — pending broker confirmation",
                            action.upper(), symbol, shares, price, event.sentiment)
                await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
