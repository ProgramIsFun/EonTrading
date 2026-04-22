"""Tests for news sentiment trading pipeline."""
import asyncio
import pytest
from unittest.mock import AsyncMock
from src.common.event_bus import LocalEventBus
from src.common.events import (
    NewsEvent, SentimentEvent, TradeEvent,
    CHANNEL_NEWS, CHANNEL_SENTIMENT, CHANNEL_TRADE,
)
from src.strategies.sentiment import KeywordSentimentAnalyzer
from src.live.news_trader import NewsWatcher, SentimentTrader
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

    async def execute(self, trade: TradeEvent) -> bool:
        self.trades.append(trade)
        return True


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
        await asyncio.sleep(0.1)

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
        trader.holdings.add("TSLA")

        sentiment = SentimentEvent(
            source="test", headline="Tesla crashes", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["TSLA"],
            sentiment=-0.8, confidence=0.9, urgency="high",
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.1)

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
        await asyncio.sleep(0.1)

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
        # Publish twice
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.1)
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.1)

        assert len(broker.trades) == 1  # only one buy, already holding


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
        await asyncio.sleep(0.1)

        assert len(broker.trades) == 1
        assert broker.trades[0].symbol == "AAPL"
        assert broker.trades[0].action == "buy"
        assert "sentiment" in broker.trades[0].reason
