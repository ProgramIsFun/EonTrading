"""SentimentTrader: listens to sentiment events, decides trades, executes synchronously.

Events are queued and processed one at a time to prevent race conditions
where concurrent handlers read stale cash balances from the broker.
"""
import asyncio
import logging
from datetime import datetime, timedelta

from src.common.clock import utcnow
from src.common.log_handler import ComponentFilter
from src.common.event_bus import EventBus
from src.common.events import CHANNEL_SENTIMENT, CHANNEL_TRADE, SentimentEvent, TradeEvent
from src.common.price import get_price
from src.common.position_store import BasePositionStore
from src.live.brokers.broker import Broker
from src.common.trading_logic import TradingLogic

logger = logging.getLogger(__name__)
logger.addFilter(ComponentFilter("trader"))


class SentimentTrader:
    """Listens to sentiment events and decides trades.

    Events are queued and processed sequentially to ensure each trade
    reads a fresh cash balance from the broker.  PositionStore is the
    source of truth for open positions.
    """

    def __init__(self, bus: EventBus, logic: TradingLogic | None = None, max_hold_days: int = 0,
                 position_store: BasePositionStore | None = None, broker: Broker | None = None, **kwargs):
        self.bus = bus
        self.logic = logic or TradingLogic(**kwargs)
        self.max_hold_days = max_hold_days
        self.position_store = position_store
        self.broker = broker
        self._last_trade_at: dict[str, dict[str, datetime]] = {}
        self._dedup_seconds = 60
        self._queue: asyncio.Queue[dict] = asyncio.Queue()

    async def start(self):
        await self.bus.subscribe(CHANNEL_SENTIMENT, self._on_sentiment)
        self._process_task = asyncio.create_task(self._process_loop())
        if self.max_hold_days > 0:
            self._hold_task = asyncio.create_task(self._hold_checker())
        logger.info("SentimentTrader started (threshold=%.2f, min_confidence=%.2f, max_hold=%dd)",
                     self.logic.threshold, self.logic.min_confidence, self.max_hold_days)

    async def _on_sentiment(self, msg: dict):
        """Just enqueue — processing happens in _process_loop."""
        await self._queue.put(msg)

    async def _process_loop(self):
        """Process sentiment events one at a time.

        Each iteration: dequeue → read cash → calculate shares → execute.
        No two events can read the same stale cash value.
        """
        while True:
            msg = await self._queue.get()
            try:
                await self._handle_sentiment(msg)
            except Exception:
                logger.exception("Unhandled error processing sentiment event")
            finally:
                self._queue.task_done()

    async def _handle_sentiment(self, msg: dict):
        event = SentimentEvent.from_dict(msg)
        if not event.symbols:
            logger.info("Skipping sentiment (no symbols): %s", event.headline[:60])
            return

        event_ts = event.timestamp

        if self.position_store:
            positions = await asyncio.to_thread(self.position_store.get_positions_with_prices)
        else:
            positions = {}

        now = utcnow()

        for symbol in event.symbols:
            action = None
            if symbol in positions:
                if self.logic.should_sell_on_sentiment(event.sentiment, event.confidence, symbol, positions):
                    action = "sell"
                    shares = positions[symbol].get("qty", 1)
                    price = await asyncio.to_thread(get_price, symbol, event_ts)
                    positions.pop(symbol, None)
                else:
                    if event.confidence < self.logic.min_confidence:
                        logger.debug("Skipped %s: confidence %.2f < min %.2f",
                                     symbol, event.confidence, self.logic.min_confidence)
                        continue
                    if event.sentiment < self.logic.threshold:
                        logger.debug("Skipped %s: sentiment %.2f < threshold %.2f",
                                     symbol, event.sentiment, self.logic.threshold)
                        continue
                    price = await asyncio.to_thread(get_price, symbol, event_ts)
                    if price <= 0:
                        logger.warning("No price for %s, skipping", symbol)
                        continue
                    try:
                        cash = await self.broker.get_cash() if self.broker else 0.0
                    except Exception:
                        logger.warning("Failed to fetch cash from broker, using 0", exc_info=True)
                        cash = 0.0
                    if cash > 0:
                        shares = self.logic.should_buy(
                            event.sentiment, event.confidence, symbol,
                            positions, cash, price,
                        )
                    else:
                        logger.warning("Cash unavailable, defaulting to qty=1 for %s", symbol)
                        shares = 1
                    if shares <= 0:
                        continue
                    action = "buy"
            else:
                if event.confidence < self.logic.min_confidence:
                    logger.debug("Skipped %s: confidence %.2f < min %.2f",
                                 symbol, event.confidence, self.logic.min_confidence)
                    continue
                if event.sentiment < self.logic.threshold:
                    logger.debug("Skipped %s: sentiment %.2f < threshold %.2f",
                                 symbol, event.sentiment, self.logic.threshold)
                    continue
                price = await asyncio.to_thread(get_price, symbol, event_ts)
                if price <= 0:
                    logger.warning("No price for %s, skipping", symbol)
                    continue
                try:
                    cash = await self.broker.get_cash() if self.broker else 0.0
                except Exception:
                    logger.warning("Failed to fetch cash from broker, using 0", exc_info=True)
                    cash = 0.0
                if cash > 0:
                    shares = self.logic.should_buy(
                        event.sentiment, event.confidence, symbol,
                        positions, cash, price,
                    )
                else:
                    logger.warning("Cash unavailable, defaulting to qty=1 for %s", symbol)
                    shares = 1
                if shares <= 0:
                    continue
                action = "buy"

            last = self._last_trade_at.get(symbol, {}).get(action)
            if last and (now - last).total_seconds() < self._dedup_seconds:
                logger.debug("Dedup suppressed: %s %s (last trade %.0fs ago)",
                             action, symbol, (now - last).total_seconds())
                continue

            self._last_trade_at.setdefault(symbol, {})[action] = now
            trade = TradeEvent(
                symbol=symbol, action=action,
                reason=f"sentiment:{event.sentiment:.2f} on {event.headline[:60]}",
                timestamp=event_ts,
                price=price,
                size=float(shares) if shares else 1.0,
            )
            logger.info("%s %s qty=%d @ $%.2f (sentiment: %.2f)",
                        action.upper(), symbol, shares, price, event.sentiment)

            if self.broker:
                try:
                    order_id = await self.broker.execute(trade)
                    if order_id:
                        logger.info("Filled: %s %s (order_id=%s)", action.upper(), symbol, order_id)
                    else:
                        logger.warning("Order failed: %s %s", action.upper(), symbol)
                except Exception:
                    logger.error("Broker execution failed: %s %s", action.upper(), symbol, exc_info=True)

            await self.bus.publish(CHANNEL_TRADE, trade.to_dict())

    async def _hold_checker(self):
        while True:
            await asyncio.sleep(3600)
            if not self.position_store:
                continue
            holdings = await asyncio.to_thread(self.position_store.get_positions)
            if not holdings:
                continue
            now = utcnow()
            for symbol, entry_time in holdings.items():
                held_days = (now - entry_time).total_seconds() / 86400
                if held_days >= self.max_hold_days:
                    last = self._last_trade_at.get(symbol, {}).get("sell")
                    if last and (now - last).total_seconds() < self._dedup_seconds:
                        continue
                    self._last_trade_at.setdefault(symbol, {})["sell"] = now
                    trade = TradeEvent(
                        symbol=symbol, action="sell",
                        reason=f"max hold {self.max_hold_days}d reached",
                        timestamp=now.isoformat() + "Z",
                    )
                    logger.info("SELL %s (max hold %dd reached)", symbol, self.max_hold_days)
                    await self.bus.publish(CHANNEL_TRADE, trade.to_dict())
