"""SentimentTrader: listens to sentiment events, decides trades, publishes trade events."""
import asyncio
from datetime import datetime
from src.common.clock import clock
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_SENTIMENT, CHANNEL_TRADE, CHANNEL_FILL, SentimentEvent, TradeEvent, FillEvent
from src.common.trading_logic import TradingLogic


class SentimentTrader:
    """Listens to sentiment events and decides trades.

    Flow: decide → save pending to MongoDB → publish trade → wait for fill confirmation → confirm or rollback.
    Uses shared TradingLogic from src/common/trading_logic.py — same logic as backtest.
    """

    def __init__(self, bus: EventBus, logic: TradingLogic = None, max_hold_days: int = 0,
                 position_store=None, trade_log=None, broker=None, **kwargs):
        self.bus = bus
        self.logic = logic or TradingLogic(**kwargs)
        self.holdings: dict[str, datetime] = {}
        self.pending: dict[str, str] = {}  # symbol → "buy"/"sell" awaiting fill
        self.max_hold_days = max_hold_days
        self.position_store = position_store
        self._trades_col = trade_log
        self.broker = broker  # for cash/price queries
        if self.position_store:
            self.holdings = self.position_store.get_positions()
            if self.holdings:
                print(f"  Restored {len(self.holdings)} position(s) from store: {list(self.holdings.keys())}")

    async def start(self):
        await self.bus.subscribe(CHANNEL_SENTIMENT, self._on_sentiment)
        await self.bus.subscribe(CHANNEL_FILL, self._on_fill)
        if self.max_hold_days > 0:
            asyncio.ensure_future(self._hold_checker())

    async def _on_fill(self, msg: dict):
        """Handle broker fill confirmation — confirm or rollback position."""
        event = FillEvent.from_dict(msg)
        symbol = event.symbol
        pending_action = self.pending.pop(symbol, None)
        if not pending_action:
            return

        if event.success:
            print(f"  ✅ {event.action.upper()} {symbol} confirmed by broker")
            if self._trades_col:
                self._trades_col.insert_one({
                    "symbol": symbol, "action": pending_action,
                    "reason": event.reason, "timestamp": clock.now(),
                })
            if self.position_store:
                if pending_action == "buy":
                    self.position_store.open_position(symbol, self.holdings[symbol])
                elif pending_action == "sell":
                    self.position_store.close_position(symbol)
        else:
            # Rollback in-memory state
            print(f"  ⚠️ {event.action.upper()} {symbol} rejected by broker: {event.reason}")
            if pending_action == "buy":
                self.holdings.pop(symbol, None)
            elif pending_action == "sell":
                self.holdings[symbol] = clock.now()  # re-add (entry time lost, but safe)

    async def _hold_checker(self):
        """Background task: close positions that exceed max hold period."""
        while True:
            now = clock.now()
            for symbol in list(self.holdings.keys()):
                if symbol in self.pending:
                    continue  # skip symbols with pending orders
                entry_time = self.holdings[symbol]
                held_days = (now - entry_time).total_seconds() / 86400
                if held_days >= self.max_hold_days:
                    del self.holdings[symbol]
                    self.pending[symbol] = "sell"
                    trade = TradeEvent(
                        symbol=symbol, action="sell",
                        reason=f"max hold {self.max_hold_days}d reached",
                        timestamp=now.isoformat() + "Z",
                    )
                    print(f"  SELL {symbol} (max hold {self.max_hold_days}d reached) — pending broker confirmation")
                    await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
            await asyncio.sleep(3600)

    async def _on_sentiment(self, msg: dict):
        event = SentimentEvent.from_dict(msg)
        if not event.symbols:
            return

        for symbol in event.symbols:
            if symbol in self.pending:
                continue  # skip symbols with pending orders

            action = None
            shares = 0
            if self.logic.should_sell_on_sentiment(event.sentiment, event.confidence, symbol, self.holdings):
                action = "sell"
                # Get shares held from broker for proper sell size
                if self.broker:
                    broker_positions = await self.broker.get_positions()
                    shares = broker_positions.get(symbol, 1)
                else:
                    shares = 1
                self.holdings.pop(symbol, None)
            elif symbol not in self.holdings:
                # Use should_buy() for proper position sizing
                cash = await self.broker.get_cash() if self.broker else 0.0
                if cash > 0:
                    from src.common.price import get_price
                    price = get_price(symbol)
                    if price > 0:
                        shares = self.logic.should_buy(
                            event.sentiment, event.confidence, symbol,
                            self.holdings, cash, price,
                        )
                        if shares > 0:
                            action = "buy"
                            self.holdings[symbol] = clock.now()
                else:
                    # No broker — fallback to threshold check (backward compat)
                    if event.confidence >= self.logic.min_confidence and event.sentiment >= self.logic.threshold:
                        action = "buy"
                        shares = 1
                        self.holdings[symbol] = clock.now()

            if action:
                self.pending[symbol] = action
                from src.common.price import get_price
                price = get_price(symbol) if action == "buy" or self.broker else 0.0
                if action == "sell":
                    price = get_price(symbol)
                trade = TradeEvent(
                    symbol=symbol, action=action,
                    reason=f"sentiment:{event.sentiment:.2f} on {event.headline[:60]}",
                    timestamp=clock.now().isoformat() + "Z",
                    price=price,
                    size=float(shares) if shares else 1.0,
                )
                print(f"  {action.upper()} {symbol} qty={shares} (sentiment: {event.sentiment:.2f}) — pending broker confirmation")
                await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
