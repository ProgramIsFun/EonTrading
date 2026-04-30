"""Tests for news sentiment trading pipeline."""
import asyncio
import pytest
from unittest.mock import AsyncMock
from datetime import datetime
from src.common.clock import utcnow
from src.common.event_bus import LocalEventBus
from src.common.events import (
    NewsEvent, SentimentEvent, TradeEvent, FillEvent,
    CHANNEL_NEWS, CHANNEL_SENTIMENT, CHANNEL_TRADE, CHANNEL_FILL,
)
from src.strategies.sentiment import KeywordSentimentAnalyzer
from src.live.news_watcher import NewsWatcher
from src.live.sentiment_trader import SentimentTrader
from src.live.brokers.broker import Broker, TradeExecutor


# --- Fake news fixtures ---

BULLISH_NEWS = NewsEvent(
    source="test", headline="Apple stock surges to record high after beating earnings",
    timestamp="2026-04-22T10:00:00Z", body="Apple reported strong growth and profit.",
)

BEARISH_NEWS = NewsEvent(
    source="test", headline="Tesla stock crashes after tariff ban and recession fears",
    timestamp="2026-04-22T10:01:00Z", body="Tesla plunges amid layoff and weak demand.",
)

NEUTRAL_NEWS = NewsEvent(
    source="test", headline="Weather forecast for tomorrow is sunny",
    timestamp="2026-04-22T10:02:00Z", body="Nothing to do with stocks.",
)


# --- Mock broker ---

class MockBroker(Broker):
    def __init__(self):
        self.trades: list[TradeEvent] = []

    async def execute(self, trade: TradeEvent):
        self.trades.append(trade)
        await self._publish_fill(trade.symbol, trade.action, True, "filled (mock)")

    async def get_positions(self) -> dict[str, int]:
        return {}


# --- Keyword sentiment tests ---

class TestKeywordSentiment:
    def setup_method(self):
        self.analyzer = KeywordSentimentAnalyzer()

    def test_bullish_news_positive_sentiment(self):
        result = self.analyzer.analyze(BULLISH_NEWS)
        assert result.sentiment > 0
        assert result.confidence > 0
        assert "AAPL" in result.symbols

    def test_bearish_news_negative_sentiment(self):
        result = self.analyzer.analyze(BEARISH_NEWS)
        assert result.sentiment < 0
        assert result.confidence > 0
        assert "TSLA" in result.symbols

    def test_neutral_news_zero_confidence(self):
        result = self.analyzer.analyze(NEUTRAL_NEWS)
        assert result.confidence == 0.0

    def test_urgency_high_on_crash(self):
        result = self.analyzer.analyze(BEARISH_NEWS)
        assert result.urgency == "high"

    def test_urgency_normal_on_mild_news(self):
        mild = NewsEvent(source="test", headline="Microsoft reports steady growth",
                         timestamp="2026-04-22T10:00:00Z", body="Profit increased.")
        result = self.analyzer.analyze(mild)
        assert result.urgency == "normal"


# --- SentimentTrader tests ---

class TestSentimentTrader:
    @pytest.fixture
    def setup(self):
        bus = LocalEventBus()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2)
        broker = MockBroker()
        executor = TradeExecutor(bus, broker)
        return bus, trader, executor, broker

    @pytest.mark.asyncio
    async def test_buy_on_bullish_sentiment(self, setup):
        bus, trader, executor, broker = setup
        await bus.start()
        await trader.start()
        await executor.start()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9, urgency="high",
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        assert len(broker.trades) == 1
        assert broker.trades[0].symbol == "AAPL"
        assert broker.trades[0].action == "buy"

    @pytest.mark.asyncio
    async def test_sell_on_bearish_sentiment(self, setup):
        bus, trader, executor, broker = setup
        await bus.start()
        await trader.start()
        await executor.start()

        # First buy
        trader.holdings["TSLA"] = utcnow()

        sentiment = SentimentEvent(
            source="test", headline="Tesla crashes", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["TSLA"],
            sentiment=-0.8, confidence=0.9, urgency="high",
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        assert len(broker.trades) == 1
        assert broker.trades[0].symbol == "TSLA"
        assert broker.trades[0].action == "sell"

    @pytest.mark.asyncio
    async def test_no_trade_on_low_confidence(self, setup):
        bus, trader, executor, broker = setup
        await bus.start()
        await trader.start()
        await executor.start()

        sentiment = SentimentEvent(
            source="test", headline="Something", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.9, confidence=0.05,  # below min_confidence
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        assert len(broker.trades) == 0

    @pytest.mark.asyncio
    async def test_no_duplicate_buy(self, setup):
        bus, trader, executor, broker = setup
        await bus.start()
        await trader.start()
        await executor.start()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        # Publish twice — second should be skipped (pending then held)
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        assert len(broker.trades) == 1  # only one buy


# --- Full pipeline test ---

class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_news_to_trade(self):
        """End-to-end: fake news → sentiment → trade signal → mock broker."""
        bus = LocalEventBus()
        await bus.start()

        analyzer = KeywordSentimentAnalyzer()
        broker = MockBroker()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2)
        executor = TradeExecutor(bus, broker)
        await trader.start()
        await executor.start()

        # Simulate what NewsWatcher does
        sentiment = analyzer.analyze(BULLISH_NEWS)
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        assert len(broker.trades) == 1
        assert broker.trades[0].symbol == "AAPL"
        assert broker.trades[0].action == "buy"
        assert "sentiment" in broker.trades[0].reason


# --- Rejecting broker for rollback tests ---

class RejectingBroker(Broker):
    """Broker that always rejects orders."""
    def __init__(self):
        self.trades: list[TradeEvent] = []

    async def execute(self, trade: TradeEvent):
        self.trades.append(trade)
        await self._publish_fill(trade.symbol, trade.action, False, "rejected by broker")

    async def get_positions(self) -> dict[str, int]:
        return {}


# --- FillEvent tests ---

class TestFillEvent:
    def test_fill_event_roundtrip(self):
        fill = FillEvent(symbol="AAPL", action="buy", success=True, reason="filled", timestamp="2026-04-22T10:00:00Z")
        d = fill.to_dict()
        restored = FillEvent.from_dict(d)
        assert restored.symbol == "AAPL"
        assert restored.success is True
        assert restored.reason == "filled"

    def test_fill_event_failure(self):
        fill = FillEvent(symbol="TSLA", action="sell", success=False, reason="timeout", timestamp="2026-04-22T10:00:00Z")
        assert fill.success is False
        assert fill.reason == "timeout"


# --- Fill confirmation & rollback tests ---

class TestFillConfirmation:
    @pytest.fixture
    def setup_with_mock(self):
        bus = LocalEventBus()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2)
        broker = MockBroker()
        executor = TradeExecutor(bus, broker)
        return bus, trader, executor, broker

    @pytest.fixture
    def setup_with_rejecting(self):
        bus = LocalEventBus()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2)
        broker = RejectingBroker()
        executor = TradeExecutor(bus, broker)
        return bus, trader, executor, broker

    @pytest.mark.asyncio
    async def test_buy_confirmed_adds_to_holdings(self, setup_with_mock):
        bus, trader, executor, broker = setup_with_mock
        await bus.start()
        await trader.start()
        await executor.start()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        assert "AAPL" in trader.holdings
        assert "AAPL" not in trader.pending

    @pytest.mark.asyncio
    async def test_buy_rejected_rolls_back(self, setup_with_rejecting):
        bus, trader, executor, broker = setup_with_rejecting
        await bus.start()
        await trader.start()
        await executor.start()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        # Broker rejected → should not be in holdings
        assert "AAPL" not in trader.holdings
        assert "AAPL" not in trader.pending

    @pytest.mark.asyncio
    async def test_sell_rejected_restores_holding(self, setup_with_rejecting):
        bus, trader, executor, broker = setup_with_rejecting
        await bus.start()
        await trader.start()
        await executor.start()

        # Pre-load a holding
        trader.holdings["TSLA"] = utcnow()

        sentiment = SentimentEvent(
            source="test", headline="Tesla crashes", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["TSLA"],
            sentiment=-0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        # Broker rejected sell → should still be in holdings
        assert "TSLA" in trader.holdings
        assert "TSLA" not in trader.pending

    @pytest.mark.asyncio
    async def test_pending_blocks_duplicate_orders(self, setup_with_mock):
        bus, trader, executor, broker = setup_with_mock
        await bus.start()
        await trader.start()
        # Don't start executor — orders stay pending forever

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.1)

        assert "AAPL" in trader.pending

        # Second event for same symbol — should be skipped
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.1)

        # Still only one trade published
        trades = []
        await bus.subscribe(CHANNEL_TRADE, lambda msg: trades.append(msg))
        # The trade was already published before we subscribed, check pending
        assert trader.pending.get("AAPL")["action"] == "buy"

    @pytest.mark.asyncio
    async def test_sell_confirmed_removes_from_holdings(self, setup_with_mock):
        bus, trader, executor, broker = setup_with_mock
        await bus.start()
        await trader.start()
        await executor.start()

        trader.holdings["TSLA"] = utcnow()

        sentiment = SentimentEvent(
            source="test", headline="Tesla crashes", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["TSLA"],
            sentiment=-0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        assert "TSLA" not in trader.holdings
        assert "TSLA" not in trader.pending


# --- Position store integration with trader ---

class TestTraderWithPositionStore:
    @pytest.mark.asyncio
    async def test_restore_positions_on_init(self):
        """Trader should restore holdings from position store on startup."""
        from unittest.mock import MagicMock
        mock_store = MagicMock()
        now = utcnow()
        mock_store.get_positions.return_value = {"AAPL": now, "NVDA": now}

        bus = LocalEventBus()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, position_store=mock_store)

        assert "AAPL" in trader.holdings
        assert "NVDA" in trader.holdings
        mock_store.get_positions.assert_called_once()

    @pytest.mark.asyncio
    async def test_fill_persists_to_store(self):
        """On confirmed fill, trader should write to position store."""
        from unittest.mock import MagicMock
        mock_store = MagicMock()
        mock_store.get_positions.return_value = {}

        bus = LocalEventBus()
        await bus.start()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, position_store=mock_store)
        broker = MockBroker()
        executor = TradeExecutor(bus, broker)
        await trader.start()
        await executor.start()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        mock_store.open_position.assert_called_once()
        assert mock_store.open_position.call_args[0][0] == "AAPL"

    @pytest.mark.asyncio
    async def test_rejected_fill_does_not_persist(self):
        """On rejected fill, trader should NOT write to position store."""
        from unittest.mock import MagicMock
        mock_store = MagicMock()
        mock_store.get_positions.return_value = {}

        bus = LocalEventBus()
        await bus.start()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, position_store=mock_store)
        broker = RejectingBroker()
        executor = TradeExecutor(bus, broker)
        await trader.start()
        await executor.start()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        mock_store.open_position.assert_not_called()
        mock_store.close_position.assert_not_called()
