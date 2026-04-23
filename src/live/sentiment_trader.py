"""SentimentTrader: listens to sentiment events, decides trades, publishes trade events."""
import asyncio
from datetime import datetime
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_SENTIMENT, CHANNEL_TRADE, SentimentEvent, TradeEvent
from src.common.trading_logic import TradingLogic


class SentimentTrader:
    """Listens to sentiment events and decides trades.

    Uses shared TradingLogic from src/common/trading_logic.py — same logic as backtest.
    """

    def __init__(self, bus: EventBus, logic: TradingLogic = None, max_hold_days: int = 0, **kwargs):
        self.bus = bus
        self.logic = logic or TradingLogic(**kwargs)
        self.holdings: dict[str, datetime] = {}
        self.max_hold_days = max_hold_days

    async def start(self):
        await self.bus.subscribe(CHANNEL_SENTIMENT, self._on_sentiment)
        if self.max_hold_days > 0:
            asyncio.ensure_future(self._hold_checker())

    async def _hold_checker(self):
        """Background task: close positions that exceed max hold period."""
        while True:
            now = datetime.utcnow()
            for symbol in list(self.holdings.keys()):
                entry_time = self.holdings[symbol]
                held_days = (now - entry_time).total_seconds() / 86400
                if held_days >= self.max_hold_days:
                    trade = TradeEvent(
                        symbol=symbol, action="sell",
                        reason=f"max hold {self.max_hold_days}d reached",
                        timestamp=now.isoformat() + "Z",
                    )
                    print(f"  SELL {symbol} (max hold {self.max_hold_days}d reached)")
                    await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
                    del self.holdings[symbol]
            await asyncio.sleep(3600)

    async def _on_sentiment(self, msg: dict):
        event = SentimentEvent.from_dict(msg)
        if not event.symbols:
            return

        for symbol in event.symbols:
            action = None
            if self.logic.should_sell_on_sentiment(event.sentiment, event.confidence, symbol, self.holdings):
                action = "sell"
                self.holdings.pop(symbol, None)
            elif event.confidence >= self.logic.min_confidence and event.sentiment >= self.logic.threshold and symbol not in self.holdings:
                action = "buy"
                self.holdings[symbol] = datetime.utcnow()

            if action:
                trade = TradeEvent(
                    symbol=symbol, action=action,
                    reason=f"sentiment:{event.sentiment} on {event.headline[:60]}",
                    timestamp=datetime.utcnow().isoformat() + "Z",
                )
                print(f"  {action.upper()} {symbol} (sentiment: {event.sentiment}, headline: {event.headline[:60]})")
                await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
