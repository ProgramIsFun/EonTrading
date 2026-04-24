"""Integration tests — full pipeline end-to-end with real components, mocked externals.

No real API keys, no MongoDB, no Redis, no yfinance calls.
Tests verify that components wire together correctly through the event bus.
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from src.common.event_bus import LocalEventBus
from src.common.events import (
    NewsEvent, SentimentEvent, TradeEvent, FillEvent,
    CHANNEL_NEWS, CHANNEL_SENTIMENT, CHANNEL_TRADE, CHANNEL_FILL,
)
from src.strategies.sentiment import KeywordSentimentAnalyzer
from src.live.analyzer_service import AnalyzerService
from src.live.sentiment_trader import SentimentTrader
from src.live.brokers.broker import PaperBroker, TradeExecutor
from src.live.price_monitor import PriceMonitor
from src.common.trading_logic import TradingLogic, PositionState
from src.common.costs import US_STOCKS


# --- Helpers ---

def make_news(headline, ts="2026-04-22T10:00:00Z"):
    return NewsEvent(source="test", headline=headline, timestamp=ts, body=headline)


BULLISH_APPLE = make_news("Apple stock surges to record high after beating earnings")
BEARISH_TESLA = make_news("Tesla stock crashes after tariff ban and recession fears", "2026-04-22T10:01:00Z")
BULLISH_NVIDIA = make_news("Nvidia rallies on strong AI chip demand and record revenue", "2026-04-22T10:02:00Z")


def mock_position_store():
    store = MagicMock()
    store.get_positions.return_value = {}
    store.get_positions_with_prices.return_value = {}
    return store


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
# 1. Full pipeline: news → analyzer → trader → executor → fill
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:
    """News goes in one end, fills come out the other."""

    @pytest.mark.asyncio
    async def test_news_flows_through_entire_pipeline(self):
        bus = LocalEventBus()
        await bus.start()

        fills = []
        await bus.subscribe(CHANNEL_FILL, fill_collector(fills))

        store = mock_position_store()
        analyzer = KeywordSentimentAnalyzer()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)

        analyzer_svc = AnalyzerService(bus, analyzer=analyzer)
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        # Publish raw news — should flow: news → sentiment → trade → fill
        with patch("src.common.price.get_price", return_value=150.0):
            await bus.publish(CHANNEL_NEWS, BULLISH_APPLE.to_dict())
            await asyncio.sleep(0.3)

        assert len(fills) == 1
        assert fills[0].symbol == "AAPL"
        assert fills[0].action == "buy"
        assert fills[0].success is True
        assert "AAPL" in trader.holdings

    @pytest.mark.asyncio
    async def test_buy_then_sell_on_sentiment_reversal(self):
        bus = LocalEventBus()
        await bus.start()

        fills = []
        await bus.subscribe(CHANNEL_FILL, fill_collector(fills))

        store = mock_position_store()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)

        analyzer_svc = AnalyzerService(bus, analyzer=KeywordSentimentAnalyzer())
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        with patch("src.common.price.get_price", return_value=250.0):
            # Buy on bullish news
            await bus.publish(CHANNEL_NEWS, make_news("Tesla surges on record deliveries and strong growth").to_dict())
            await asyncio.sleep(0.3)

            assert "TSLA" in trader.holdings
            assert fills[-1].action == "buy"

            # Sell on bearish news
            await bus.publish(CHANNEL_NEWS, BEARISH_TESLA.to_dict())
            await asyncio.sleep(0.3)

        assert "TSLA" not in trader.holdings
        assert fills[-1].action == "sell"
        assert len(fills) == 2

    @pytest.mark.asyncio
    async def test_multiple_symbols_independent(self):
        bus = LocalEventBus()
        await bus.start()

        fills = []
        await bus.subscribe(CHANNEL_FILL, fill_collector(fills))

        store = mock_position_store()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)

        analyzer_svc = AnalyzerService(bus, analyzer=KeywordSentimentAnalyzer())
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

        assert "AAPL" in trader.holdings
        assert "NVDA" in trader.holdings
        assert len(fills) == 2
        symbols_filled = {f.symbol for f in fills}
        assert symbols_filled == {"AAPL", "NVDA"}


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

        await trader.start()
        await executor.start()

        # Simulate: trader bought AAPL at $150
        with patch("src.common.price.get_price", return_value=150.0):
            await bus.publish(CHANNEL_SENTIMENT, SentimentEvent(
                source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
                analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
                sentiment=0.8, confidence=0.9,
            ).to_dict())
            await asyncio.sleep(0.3)

        assert "AAPL" in trader.holdings
        broker_pos = await broker.get_positions()
        assert "AAPL" in broker_pos

        # Now SL triggers at $140 (>5% drop from $150)
        with patch("src.common.price.get_price", return_value=140.0):
            sold = await monitor.check_once(broker, as_of="2026-04-22T14:00:00Z")
            await asyncio.sleep(0.3)

        assert "AAPL" in sold
        # Executor processed the sell → broker position cleared
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
        svc = AnalyzerService(bus, analyzer=analyzer, get_positions=lambda: positions)
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

        analyzer_svc = AnalyzerService(bus, analyzer=KeywordSentimentAnalyzer())
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        neutral = make_news("Weather forecast for tomorrow is sunny and warm")
        await bus.publish(CHANNEL_NEWS, neutral.to_dict())
        await asyncio.sleep(0.3)

        assert len(fills) == 0
        assert len(trader.holdings) == 0


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
