"""Integration tests — full pipeline end-to-end with real components, mocked externals.

No real API keys, no MongoDB, no Redis, no yfinance calls.
Tests verify that components wire together correctly through the event bus.
"""
import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest

from src.common.costs import US_STOCKS
from src.common.event_bus import LocalEventBus
from src.common.events import (
    CHANNEL_FILL,
    CHANNEL_NEWS,
    CHANNEL_SENTIMENT,
    CHANNEL_TRADE,
    FillEvent,
    NewsEvent,
    SentimentEvent,
    TradeEvent,
)
from src.common.trading_logic import PositionState, TradingLogic
from src.live.analyzer_service import AnalyzerService
from src.live.brokers.broker import PaperBroker, TradeExecutor
from src.live.price_monitor import PriceMonitor
from src.live.sentiment_trader import SentimentTrader
from src.strategies.sentiment import KeywordSentimentAnalyzer


@pytest.fixture(autouse=True)
def mock_get_price():
    with patch("src.live.sentiment_trader.get_price", return_value=150.0):
        yield


# --- Helpers ---

def make_news(headline, ts="2026-04-22T10:00:00Z"):
    return NewsEvent(source="test", headline=headline, timestamp=ts, body=headline)


BULLISH_APPLE = make_news("Apple stock surges to record high after beating earnings")
BEARISH_TESLA = make_news("Tesla stock crashes after tariff ban and recession fears", "2026-04-22T10:01:00Z")
BULLISH_NVIDIA = make_news("Nvidia rallies on strong AI chip demand and record revenue", "2026-04-22T10:02:00Z")


class FakePositionStore:
    """In-memory PositionStore — tracks state for integration tests."""
    def __init__(self):
        self._positions: dict[str, datetime] = {}
    def get_positions(self):
        return dict(self._positions)
    def get_positions_with_prices(self):
        return {s: {"entryTime": t, "entryPrice": 0.0} for s, t in self._positions.items()}
    def open_position(self, symbol, entry_time, entry_price=0.0, qty=0):
        self._positions[symbol] = entry_time
    def close_position(self, symbol):
        self._positions.pop(symbol, None)
    def set_positions(self, holdings, entry_prices=None):
        self._positions = dict(holdings)


def mock_position_store():
    return FakePositionStore()


def collector(lst):
    """Async subscriber that appends raw messages to a list."""
    async def _handler(msg):
        lst.append(msg)
    return _handler


def fill_collector(lst):
    """Async subscriber that parses FillEvents."""
    async def _handler(msg):
        lst.append(FillEvent.from_dict(msg))
    return _handler


def trade_collector(lst):
    """Async subscriber that parses TradeEvents."""
    async def _handler(msg):
        lst.append(TradeEvent.from_dict(msg))
    return _handler


# ---------------------------------------------------------------------------
# 1. Full pipeline: news → analyzer → trader → executor → pending_orders
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:
    """News goes in one end, trades come out the other."""

    @pytest.mark.asyncio
    async def test_news_flows_through_entire_pipeline(self):
        bus = LocalEventBus()
        await bus.start()

        trades = []
        await bus.subscribe(CHANNEL_TRADE, trade_collector(trades))

        store = mock_position_store()
        analyzer = KeywordSentimentAnalyzer()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)

        analyzer_svc = AnalyzerService(bus, analyzer=analyzer, max_age_sec=0)
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        # Publish raw news — should flow: news → sentiment → trade
        with patch("src.common.price.get_price", return_value=150.0):
            await bus.publish(CHANNEL_NEWS, BULLISH_APPLE.to_dict())
            await asyncio.sleep(0.3)

        assert len(trades) == 1
        assert trades[0].symbol == "AAPL"
        assert trades[0].action == "buy"
        broker_pos = await broker.get_positions()
        assert "AAPL" in broker_pos

    @pytest.mark.asyncio
    async def test_buy_then_sell_on_sentiment_reversal(self):
        bus = LocalEventBus()
        await bus.start()

        trades = []
        store = mock_position_store()

        async def on_trade(msg):
            t = TradeEvent.from_dict(msg)
            trades.append(t)
            if t.action == "buy":
                store.open_position(t.symbol, datetime.utcnow(), t.price)
            elif t.action == "sell":
                store.close_position(t.symbol)

        await bus.subscribe(CHANNEL_TRADE, on_trade)

        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)

        analyzer_svc = AnalyzerService(bus, analyzer=KeywordSentimentAnalyzer(), max_age_sec=0)
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        with patch("src.common.price.get_price", return_value=250.0):
            # Buy on bullish news
            await bus.publish(CHANNEL_NEWS, make_news("Tesla surges on record deliveries and strong growth").to_dict())
            await asyncio.sleep(0.3)

            broker_pos = await broker.get_positions()
            assert "TSLA" in broker_pos
            assert trades[-1].action == "buy"

            # Sell on bearish news — trader reads position_store to detect holding
            await bus.publish(CHANNEL_NEWS, BEARISH_TESLA.to_dict())
            await asyncio.sleep(0.3)

        broker_pos = await broker.get_positions()
        assert "TSLA" not in broker_pos
        assert trades[-1].action == "sell"
        assert len(trades) == 2

    @pytest.mark.asyncio
    async def test_multiple_symbols_independent(self):
        bus = LocalEventBus()
        await bus.start()

        trades = []
        await bus.subscribe(CHANNEL_TRADE, trade_collector(trades))

        store = mock_position_store()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)

        analyzer_svc = AnalyzerService(bus, analyzer=KeywordSentimentAnalyzer(), max_age_sec=0)
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        with patch("src.common.price.get_price", return_value=150.0):
            await bus.publish(CHANNEL_NEWS, BULLISH_APPLE.to_dict())
            await asyncio.sleep(0.2)
            await bus.publish(CHANNEL_NEWS, BULLISH_NVIDIA.to_dict())
            await asyncio.sleep(0.2)

        broker_pos = await broker.get_positions()
        assert "AAPL" in broker_pos
        assert "NVDA" in broker_pos
        assert len(trades) == 2
        assert {t.symbol for t in trades} == {"AAPL", "NVDA"}


# ---------------------------------------------------------------------------
# 2. PaperBroker cash tracking through pipeline
# ---------------------------------------------------------------------------

class TestBrokerCashIntegration:

    @pytest.mark.asyncio
    async def test_cash_decreases_on_buy(self):
        bus = LocalEventBus()
        await bus.start()

        broker = PaperBroker(initial_cash=50000, cost_model=US_STOCKS)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)
        store = mock_position_store()

        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)
        await trader.start()
        await executor.start()

        initial_cash = await broker.get_cash()

        with patch("src.common.price.get_price", return_value=150.0):
            sentiment = SentimentEvent(
                source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
                analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
                sentiment=0.8, confidence=0.9,
            )
            await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
            await asyncio.sleep(0.3)

        final_cash = await broker.get_cash()
        positions = await broker.get_positions()

        assert final_cash < initial_cash
        assert "AAPL" in positions
        assert positions["AAPL"] > 0

    @pytest.mark.asyncio
    async def test_cash_restored_on_sell(self):
        bus = LocalEventBus()
        await bus.start()

        broker = PaperBroker(initial_cash=50000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)
        store = mock_position_store()

        async def on_trade(msg):
            t = TradeEvent.from_dict(msg)
            if t.action == "buy":
                store.open_position(t.symbol, datetime.utcnow(), t.price)
            elif t.action == "sell":
                store.close_position(t.symbol)

        await bus.subscribe(CHANNEL_TRADE, on_trade)

        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)
        await trader.start()
        await executor.start()

        with patch("src.common.price.get_price", return_value=100.0):
            # Buy
            await bus.publish(CHANNEL_SENTIMENT, SentimentEvent(
                source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
                analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
                sentiment=0.8, confidence=0.9,
            ).to_dict())
            await asyncio.sleep(0.3)

            cash_after_buy = await broker.get_cash()

            # Sell
            await bus.publish(CHANNEL_SENTIMENT, SentimentEvent(
                source="test", headline="Apple crashes", timestamp="2026-04-22T11:00:00Z",
                analyzed_at="2026-04-22T11:00:01Z", symbols=["AAPL"],
                sentiment=-0.8, confidence=0.9,
            ).to_dict())
            await asyncio.sleep(0.3)

        cash_after_sell = await broker.get_cash()
        assert cash_after_sell > cash_after_buy
        assert (await broker.get_positions()).get("AAPL", 0) == 0


# ---------------------------------------------------------------------------
# 3. PriceMonitor SL/TP integration
# ---------------------------------------------------------------------------

class TestPriceMonitorIntegration:

    @pytest.mark.asyncio
    async def test_stop_loss_triggers_sell_trade(self):
        bus = LocalEventBus()
        await bus.start()

        trades = []
        await bus.subscribe(CHANNEL_TRADE, trade_collector(trades))

        store = mock_position_store()
        logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
        monitor = PriceMonitor(bus, store, logic)

        # Register a position at $100
        monitor.register_entry("AAPL", 100.0, 10)

        # Price drops to $94 (6% drop, exceeds 5% SL)
        with patch("src.live.price_monitor.get_price", return_value=94.0):
            sold = await monitor.check_once(as_of="2026-04-22T12:00:00Z")
            await asyncio.sleep(0.1)

        assert "AAPL" in sold
        assert len(trades) == 1
        assert trades[0].action == "sell"
        assert "stop loss" in trades[0].reason

    @pytest.mark.asyncio
    async def test_take_profit_triggers_sell_trade(self):
        bus = LocalEventBus()
        await bus.start()

        trades = []
        await bus.subscribe(CHANNEL_TRADE, trade_collector(trades))

        store = mock_position_store()
        logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
        monitor = PriceMonitor(bus, store, logic)

        monitor.register_entry("NVDA", 200.0, 5)

        # Price rises to $222 (11% gain, exceeds 10% TP)
        with patch("src.live.price_monitor.get_price", return_value=222.0):
            sold = await monitor.check_once(as_of="2026-04-22T12:00:00Z")
            await asyncio.sleep(0.1)

        assert "NVDA" in sold
        assert len(trades) == 1
        assert "take profit" in trades[0].reason

    @pytest.mark.asyncio
    async def test_no_trigger_within_bounds(self):
        bus = LocalEventBus()
        await bus.start()

        trades = []
        await bus.subscribe(CHANNEL_TRADE, trade_collector(trades))

        store = mock_position_store()
        logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
        monitor = PriceMonitor(bus, store, logic)

        monitor.register_entry("AAPL", 100.0, 10)

        # Price at $97 (3% drop, within 5% SL)
        with patch("src.live.price_monitor.get_price", return_value=97.0):
            sold = await monitor.check_once(as_of="2026-04-22T12:00:00Z")

        assert sold == []
        assert len(trades) == 0

    def test_sync_stop_loss_for_backtest(self):
        bus = LocalEventBus()
        store = mock_position_store()
        logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
        monitor = PriceMonitor(bus, store, logic)

        monitor.register_entry("AAPL", 100.0, 10)

        with patch("src.common.price.get_price", return_value=94.0):
            sold = monitor.check_once_sync(as_of="2026-04-22T12:00:00Z")

        assert len(sold) == 1
        assert sold[0][0] == "AAPL"  # symbol
        assert sold[0][2] == 10      # shares


# ---------------------------------------------------------------------------
# 4. SL/TP → Executor → Fill → Trader position cleanup
# ---------------------------------------------------------------------------

class TestSLTPFullCycle:

    @pytest.mark.asyncio
    async def test_sl_sell_flows_through_executor_and_updates_trader(self):
        """PriceMonitor triggers SL → trade event → executor → fill → trader removes holding."""
        bus = LocalEventBus()
        await bus.start()

        store = mock_position_store()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2,
                             stop_loss_pct=0.05, take_profit_pct=0.10)

        monitor = PriceMonitor(bus, store, logic)
        trader = SentimentTrader(bus, logic=logic, broker=broker,
                                 position_store=store, price_monitor=monitor)
        executor = TradeExecutor(bus, broker)

        async def on_trade(msg):
            t = TradeEvent.from_dict(msg)
            if t.action == "buy":
                store.open_position(t.symbol, datetime.utcnow(), t.price)
                monitor.register_entry(t.symbol, t.price, int(t.size))

        await bus.subscribe(CHANNEL_TRADE, on_trade)
        await trader.start()
        await executor.start()

        # Simulate: trader bought AAPL at $150
        with patch("src.common.price.get_price", return_value=150.0), \
             patch("src.live.price_monitor.get_price", return_value=150.0):
            await bus.publish(CHANNEL_SENTIMENT, SentimentEvent(
                source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
                analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
                sentiment=0.8, confidence=0.9,
            ).to_dict())
            await asyncio.sleep(0.3)

        broker_pos = await broker.get_positions()
        assert "AAPL" in broker_pos

        # Now SL triggers at $140 (>5% drop from $150)
        with patch("src.common.price.get_price", return_value=140.0), \
             patch("src.live.price_monitor.get_price", return_value=140.0):
            sold = await monitor.check_once(as_of="2026-04-22T14:00:00Z")
            await asyncio.sleep(0.3)

        assert "AAPL" in sold
        # Executor processed the sell → broker position cleared
        await asyncio.sleep(0.2)
        broker_pos = await broker.get_positions()
        assert broker_pos.get("AAPL", 0) == 0


# ---------------------------------------------------------------------------
# 5. Analyzer with portfolio context
# ---------------------------------------------------------------------------

class TestAnalyzerPositionAware:

    @pytest.mark.asyncio
    async def test_analyzer_receives_current_positions(self):
        bus = LocalEventBus()
        await bus.start()

        sentiments = []
        await bus.subscribe(CHANNEL_SENTIMENT, collector(sentiments))

        positions = {"AAPL": 100}
        analyzer = KeywordSentimentAnalyzer()
        svc = AnalyzerService(bus, analyzer=analyzer, get_positions=lambda: positions, max_age_sec=0)
        await svc.start()

        await bus.publish(CHANNEL_NEWS, BULLISH_APPLE.to_dict())
        await asyncio.sleep(0.2)

        assert len(sentiments) >= 1
        assert "AAPL" in sentiments[0].get("symbols", [])


# ---------------------------------------------------------------------------
# 6. Neutral news produces no trades
# ---------------------------------------------------------------------------

class TestNeutralNewsNoTrades:

    @pytest.mark.asyncio
    async def test_irrelevant_news_produces_no_fills(self):
        bus = LocalEventBus()
        await bus.start()

        fills = []
        await bus.subscribe(CHANNEL_FILL, fill_collector(fills))

        store = mock_position_store()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2)

        analyzer_svc = AnalyzerService(bus, analyzer=KeywordSentimentAnalyzer(), max_age_sec=0)
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        neutral = make_news("Weather forecast for tomorrow is sunny and warm")
        await bus.publish(CHANNEL_NEWS, neutral.to_dict())
        await asyncio.sleep(0.3)

        assert len(fills) == 0
        broker_pos = await broker.get_positions()
        assert len(broker_pos) == 0


# ---------------------------------------------------------------------------
# 7. Position sizing respects max_allocation
# ---------------------------------------------------------------------------

class TestPositionSizing:

    @pytest.mark.asyncio
    async def test_max_allocation_limits_position_size(self):
        bus = LocalEventBus()
        await bus.start()

        broker = PaperBroker(initial_cash=100000)
        # 10% max allocation = $10,000 max per trade
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.10)
        store = mock_position_store()

        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)
        await trader.start()
        await executor.start()

        with patch("src.common.price.get_price", return_value=100.0):
            await bus.publish(CHANNEL_SENTIMENT, SentimentEvent(
                source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
                analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
                sentiment=0.8, confidence=0.9,
            ).to_dict())
            await asyncio.sleep(0.3)

        positions = await broker.get_positions()
        # At $100/share, 10% of $100k = $10k = 100 shares max
        assert positions["AAPL"] <= 100
        # But should have bought something
        assert positions["AAPL"] > 0
