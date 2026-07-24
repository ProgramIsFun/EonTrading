"""Integration tests — full pipeline end-to-end with real components, mocked externals.

No real API keys, no MongoDB, no Redis, no yfinance calls.
Tests verify that components wire together correctly through the event bus.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from tests.helpers import Collector, FakePositionStore

from src.common.costs import US_STOCKS
from src.common.event_bus import LocalEventBus
from src.common.events import (
    CHANNEL_NEWS,
    CHANNEL_SENTIMENT,
    CHANNEL_TRADE,
    NewsEvent,
    SentimentEvent,
    TradeEvent,
)
from src.common.trading_logic import TradingLogic
from src.live.analyzer_service import AnalyzerService
from src.live.brokers.broker import PaperBroker, TradeExecutor
from src.live.price_monitor import PriceMonitor
from src.live.sentiment_trader import SentimentTrader
from src.strategies.sentiment import KeywordSentimentAnalyzer


@ pytest.fixture(autouse=True)
def mock_get_price():
    with patch("src.live.sentiment_trader.get_price", return_value=150.0), \
         patch("src.live.price_monitor.get_price", return_value=150.0), \
         patch("src.live.brokers.broker.get_price", return_value=150.0), \
         patch("src.common.price.get_price", return_value=150.0):
        yield


def make_news(headline, ts="2026-04-22T10:00:00Z"):
    return NewsEvent(source="test", headline=headline, timestamp=ts, body=headline)


BULLISH_APPLE = make_news("Apple stock surges to record high after beating earnings")
BEARISH_TESLA = make_news("Tesla stock crashes after tariff ban and recession fears", "2026-04-22T10:01:00Z")
BULLISH_NVIDIA = make_news("Nvidia rallies on strong AI chip demand and record revenue", "2026-04-22T10:02:00Z")


def track_position(store):
    """Return a callback that maintains the FakePositionStore from trade events."""
    def _(trade):
        if trade.action == "buy":
            store.open_position(trade.symbol, datetime.utcnow(), trade.price, qty=trade.size)
        elif trade.action == "sell":
            store.close_position(trade.symbol)
    return _


# ---------------------------------------------------------------------------
# 1. Full pipeline: news → analyzer → trader → executor → trades
# ---------------------------------------------------------------------------

class TestFullPipelineIntegration:
    """News goes in one end, trades come out the other."""

    @pytest.mark.asyncio
    async def test_news_flows_through_entire_pipeline(self):
        bus = LocalEventBus()
        await bus.start()

        store = FakePositionStore()
        analyzer = KeywordSentimentAnalyzer()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)

        trades = Collector(
            parser=lambda msg: TradeEvent.from_dict(msg),
            on_message=track_position(store),
        )
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        analyzer_svc = AnalyzerService(bus, analyzer=analyzer, max_age_sec=0)
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        await bus.publish(CHANNEL_NEWS, BULLISH_APPLE.to_dict())
        ok = await trades.wait_for_count(1)
        assert ok, f"Expected 1 trade, got {len(trades.items)}"

        assert trades.items[0].symbol == "AAPL"
        assert trades.items[0].action == "buy"
        broker_pos = await broker.get_positions()
        assert "AAPL" in broker_pos

    @pytest.mark.asyncio
    async def test_buy_then_sell_on_sentiment_reversal(self):
        bus = LocalEventBus()
        await bus.start()

        store = FakePositionStore()
        trades = Collector(
            parser=lambda msg: TradeEvent.from_dict(msg),
            on_message=track_position(store),
        )
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)

        analyzer_svc = AnalyzerService(bus, analyzer=KeywordSentimentAnalyzer(), max_age_sec=0)
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        # Buy on bullish news
        await bus.publish(CHANNEL_NEWS, make_news("Tesla surges on record deliveries and strong growth").to_dict())
        ok = await trades.wait_for_count(1)
        assert ok, f"Expected 1 trade after buy, got {len(trades.items)}"
        assert trades.items[-1].action == "buy"
        broker_pos = await broker.get_positions()
        assert "TSLA" in broker_pos

        # Sell on bearish news — trader reads position_store to detect holding
        await bus.publish(CHANNEL_NEWS, BEARISH_TESLA.to_dict())
        ok = await trades.wait_for_count(2)
        assert ok, f"Expected 2 trades after sell, got {len(trades.items)}"

        broker_pos = await broker.get_positions()
        assert "TSLA" not in broker_pos
        assert trades.items[-1].action == "sell"

    @pytest.mark.asyncio
    async def test_multiple_symbols_independent(self):
        bus = LocalEventBus()
        await bus.start()

        store = FakePositionStore()
        trades = Collector(
            parser=lambda msg: TradeEvent.from_dict(msg),
            on_message=track_position(store),
        )
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        analyzer = KeywordSentimentAnalyzer()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2)

        analyzer_svc = AnalyzerService(bus, analyzer=KeywordSentimentAnalyzer(), max_age_sec=0)
        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)

        await analyzer_svc.start()
        await trader.start()
        await executor.start()

        await bus.publish(CHANNEL_NEWS, BULLISH_APPLE.to_dict())
        ok = await trades.wait_for_count(1)
        assert ok, f"Expected 1 trade after AAPL news, got {len(trades.items)}"

        await bus.publish(CHANNEL_NEWS, BULLISH_NVIDIA.to_dict())
        ok = await trades.wait_for_count(2)
        assert ok, f"Expected 2 trades after NVDA news, got {len(trades.items)}"

        broker_pos = await broker.get_positions()
        assert "AAPL" in broker_pos
        assert "NVDA" in broker_pos
        assert {t.symbol for t in trades.items} == {"AAPL", "NVDA"}


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
        store = FakePositionStore()

        trades = Collector(parser=lambda msg: TradeEvent.from_dict(msg))
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)
        await trader.start()
        await executor.start()

        initial_cash = await broker.get_cash()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        ok = await trades.wait_for_count(1)
        assert ok, f"Expected 1 trade, got {len(trades.items)}"

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
        store = FakePositionStore()

        trades = Collector(
            parser=lambda msg: TradeEvent.from_dict(msg),
            on_message=track_position(store),
        )
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)
        await trader.start()
        await executor.start()

        await bus.publish(CHANNEL_SENTIMENT, SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        ).to_dict())
        ok = await trades.wait_for_count(1)
        assert ok, f"Expected 1 trade on buy, got {len(trades.items)}"

        cash_after_buy = await broker.get_cash()

        await bus.publish(CHANNEL_SENTIMENT, SentimentEvent(
            source="test", headline="Apple crashes", timestamp="2026-04-22T11:00:00Z",
            analyzed_at="2026-04-22T11:00:01Z", symbols=["AAPL"],
            sentiment=-0.8, confidence=0.9,
        ).to_dict())
        ok = await trades.wait_for_count(2)
        assert ok, f"Expected 2 trades on sell, got {len(trades.items)}"

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

        trades = Collector(parser=lambda msg: TradeEvent.from_dict(msg))
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        store = FakePositionStore()
        logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
        monitor = PriceMonitor(bus, store, logic)

        monitor.register_entry("AAPL", 100.0, 10)

        with patch("src.live.price_monitor.get_price", return_value=94.0), \
             patch("src.common.price.get_price", return_value=94.0):
            sold = await monitor.check_once(as_of="2026-04-22T12:00:00Z")
            ok = await trades.wait_for_count(1)
            assert ok, f"Expected 1 trade from SL, got {len(trades.items)}"

        assert "AAPL" in sold
        assert trades.items[0].action == "sell"
        assert trades.items[0].price == 0.0
        assert "stop loss" in trades.items[0].reason

    @pytest.mark.asyncio
    async def test_take_profit_triggers_sell_trade(self):
        bus = LocalEventBus()
        await bus.start()

        trades = Collector(parser=lambda msg: TradeEvent.from_dict(msg))
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        store = FakePositionStore()
        logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
        monitor = PriceMonitor(bus, store, logic)

        monitor.register_entry("NVDA", 200.0, 5)

        with patch("src.live.price_monitor.get_price", return_value=222.0), \
             patch("src.common.price.get_price", return_value=222.0):
            sold = await monitor.check_once(as_of="2026-04-22T12:00:00Z")
            ok = await trades.wait_for_count(1)
            assert ok, f"Expected 1 trade from TP, got {len(trades.items)}"

        assert "NVDA" in sold
        assert trades.items[0].action == "sell"
        assert trades.items[0].price == 0.0
        assert "take profit" in trades.items[0].reason

    @pytest.mark.asyncio
    async def test_no_trigger_within_bounds(self):
        bus = LocalEventBus()
        await bus.start()

        trades = Collector(parser=lambda msg: TradeEvent.from_dict(msg))
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        store = FakePositionStore()
        logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
        monitor = PriceMonitor(bus, store, logic)

        monitor.register_entry("AAPL", 100.0, 10)

        with patch("src.live.price_monitor.get_price", return_value=97.0), \
             patch("src.common.price.get_price", return_value=97.0):
            sold = await monitor.check_once(as_of="2026-04-22T12:00:00Z")
            await asyncio.sleep(0.05)

        assert sold == []
        assert len(trades.items) == 0

    def test_sync_stop_loss_for_backtest(self):
        bus = LocalEventBus()
        store = FakePositionStore()
        logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
        monitor = PriceMonitor(bus, store, logic)

        monitor.register_entry("AAPL", 100.0, 10)

        with patch("src.common.price.get_price", return_value=94.0):
            sold = monitor.check_once_sync(as_of="2026-04-22T12:00:00Z")

        assert len(sold) == 1
        assert sold[0][0] == "AAPL"
        assert sold[0][2] == 10


# ---------------------------------------------------------------------------
# 4. SL/TP → Executor → Fill → Trader position cleanup
# ---------------------------------------------------------------------------

class TestSLTPFullCycle:

    @pytest.mark.asyncio
    async def test_sl_sell_flows_through_executor_and_updates_trader(self):
        """PriceMonitor triggers SL → trade event → executor → fill → trader removes holding."""
        bus = LocalEventBus()
        await bus.start()

        store = FakePositionStore()
        broker = PaperBroker(initial_cash=100000)
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.2,
                             stop_loss_pct=0.05, take_profit_pct=0.10)

        monitor = PriceMonitor(bus, store, logic)
        trader = SentimentTrader(bus, logic=logic, broker=broker,
                                 position_store=store, price_monitor=monitor)
        executor = TradeExecutor(bus, broker)

        trades = Collector(
            parser=lambda msg: TradeEvent.from_dict(msg),
            on_message=track_position(store),
        )
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        await trader.start()
        await executor.start()

        await bus.publish(CHANNEL_SENTIMENT, SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        ).to_dict())
        ok = await trades.wait_for_count(1)
        assert ok, f"Expected 1 trade from buy, got {len(trades.items)}"

        broker_pos = await broker.get_positions()
        assert "AAPL" in broker_pos

        with patch("src.live.price_monitor.get_price", return_value=140.0), \
             patch("src.live.brokers.broker.get_price", return_value=140.0), \
             patch("src.common.price.get_price", return_value=140.0):
            sold = await monitor.check_once(as_of="2026-04-22T14:00:00Z")
            ok = await trades.wait_for_count(2)
            assert ok, f"Expected 2 trades after SL, got {len(trades.items)}"
            # publish() fires handlers as create_task — executor is a separate
            # concurrent task.  Yield so it can finish before we check the broker.
            await asyncio.sleep(0.05)

        assert "AAPL" in sold
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

        sentiments = Collector()
        await bus.subscribe(CHANNEL_SENTIMENT, sentiments.handler)

        positions = {"AAPL": 100}
        analyzer = KeywordSentimentAnalyzer()
        svc = AnalyzerService(bus, analyzer=analyzer, get_positions=lambda: positions, max_age_sec=0)
        await svc.start()

        await bus.publish(CHANNEL_NEWS, BULLISH_APPLE.to_dict())
        ok = await sentiments.wait_for_count(1)
        assert ok, f"Expected 1 sentiment, got {len(sentiments.items)}"

        assert "AAPL" in sentiments.items[0].get("symbols", [])


# ---------------------------------------------------------------------------
# 6. Neutral news produces no trades
# ---------------------------------------------------------------------------

class TestNeutralNewsNoTrades:

    @pytest.mark.asyncio
    async def test_irrelevant_news_produces_no_trades(self):
        bus = LocalEventBus()
        await bus.start()

        trades = Collector()
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        store = FakePositionStore()
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

        assert len(trades.items) == 0
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
        logic = TradingLogic(threshold=0.3, min_confidence=0.2, max_allocation=0.10)
        store = FakePositionStore()

        trades = Collector(parser=lambda msg: TradeEvent.from_dict(msg))
        await bus.subscribe(CHANNEL_TRADE, trades.handler)

        trader = SentimentTrader(bus, logic=logic, broker=broker, position_store=store)
        executor = TradeExecutor(bus, broker)
        await trader.start()
        await executor.start()

        await bus.publish(CHANNEL_SENTIMENT, SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        ).to_dict())
        ok = await trades.wait_for_count(1)
        assert ok, f"Expected 1 trade, got {len(trades.items)}"

        positions = await broker.get_positions()
        assert positions["AAPL"] <= 100
        assert positions["AAPL"] > 0


# ---------------------------------------------------------------------------
# 8. PaperBroker market order (price=0 → fetches current price)
# ---------------------------------------------------------------------------

class TestPaperBrokerMarketOrder:

    @pytest.mark.asyncio
    async def test_sell_at_market_price_when_price_zero(self):
        bus = LocalEventBus()
        await bus.start()

        broker = PaperBroker(initial_cash=50000)
        # Manually add a position
        broker._positions["AAPL"] = 100

        trade = TradeEvent(
            symbol="AAPL", action="sell", reason="test market order",
            timestamp="2026-04-22T10:00:00Z", price=0.0, size=100,
        )

        with patch("src.live.brokers.broker.get_price", return_value=200.0):
            order_id = await broker.execute(trade)

        assert order_id is not None
        assert "AAPL" not in broker._positions
        cash = await broker.get_cash()
        assert cash == 50000 + (200.0 * 100)  # initial + proceeds

    @pytest.mark.asyncio
    async def test_sell_at_specified_price_when_nonzero(self):
        bus = LocalEventBus()
        await bus.start()

        broker = PaperBroker(initial_cash=50000)
        broker._positions["AAPL"] = 100

        trade = TradeEvent(
            symbol="AAPL", action="sell", reason="test limit order",
            timestamp="2026-04-22T10:00:00Z", price=250.0, size=100,
        )

        order_id = await broker.execute(trade)
        assert order_id is not None
        assert "AAPL" not in broker._positions
        cash = await broker.get_cash()
        assert cash == 50000 + (250.0 * 100)

    @pytest.mark.asyncio
    async def test_buy_at_market_price_when_price_zero(self):
        bus = LocalEventBus()
        await bus.start()

        broker = PaperBroker(initial_cash=50000)

        trade = TradeEvent(
            symbol="AAPL", action="buy", reason="test market order",
            timestamp="2026-04-22T10:00:00Z", price=0.0, size=10,
        )

        with patch("src.live.brokers.broker.get_price", return_value=200.0):
            order_id = await broker.execute(trade)

        assert order_id is not None
        assert broker._positions["AAPL"] == 10
        cash = await broker.get_cash()
        assert cash == 50000 - (200.0 * 10)

    @pytest.mark.asyncio
    async def test_market_order_fails_when_price_unavailable(self):
        bus = LocalEventBus()
        await bus.start()

        broker = PaperBroker(initial_cash=50000)

        trade = TradeEvent(
            symbol="AAPL", action="sell", reason="test",
            timestamp="2026-04-22T10:00:00Z", price=0.0, size=10,
        )

        with patch("src.live.brokers.broker.get_price", return_value=0):
            order_id = await broker.execute(trade)

        assert order_id is None
