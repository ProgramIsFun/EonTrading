"""Tests for news sentiment trading pipeline."""
import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest
from tests.helpers import MockBroker

from unittest.mock import AsyncMock, MagicMock

from src.common.clock import utcnow
from src.common.event_bus import LocalEventBus
from src.common.events import (
    CHANNEL_NEWS,
    CHANNEL_SENTIMENT,
    CHANNEL_TRADE,
    NewsEvent,
    SentimentEvent,
    TradeEvent,
)
from src.live.brokers import Broker
from src.live.news_watcher import NewsWatcher
from src.live.sentiment_trader import SentimentTrader
from src.strategies.sentiment import KeywordSentimentAnalyzer


@pytest.fixture(autouse=True)
def mock_get_price():
    with patch("src.live.sentiment_trader.get_price", return_value=150.0):
        yield


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
        broker = MockBroker()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, broker=broker)
        return bus, trader, broker

    @pytest.mark.asyncio
    async def test_buy_on_bullish_sentiment(self, setup):
        bus, trader, broker = setup
        await bus.start()
        await trader.start()

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
        bus, trader, broker = setup
        await bus.start()
        await trader.start()

        # Pre-load position via mock store
        mock_store = MagicMock()
        mock_store.get_positions_with_prices.return_value = {
            "TSLA": {"entryTime": utcnow(), "entryPrice": 200.0, "qty": 10},
        }
        trader.position_store = mock_store

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
        bus, trader, broker = setup
        await bus.start()
        await trader.start()

        sentiment = SentimentEvent(
            source="test", headline="Something", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.9, confidence=0.05,  # below min_confidence
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        assert len(broker.trades) == 0

    @pytest.mark.asyncio
    async def test_no_trade_when_price_unavailable(self, setup):
        """If yfinance returns no data (price=0), skip the trade. Better to miss than buy at wrong price."""
        bus, trader, broker = setup
        await bus.start()
        await trader.start()

        with patch("src.live.sentiment_trader.get_price", return_value=0.0):
            sentiment = SentimentEvent(
                source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
                analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
                sentiment=0.8, confidence=0.9, urgency="high",
            )
            await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
            await asyncio.sleep(0.2)

        assert len(broker.trades) == 0  # no price = no trade

    @pytest.mark.asyncio
    async def test_no_duplicate_buy(self, setup):
        bus, trader, broker = setup
        await bus.start()
        await trader.start()

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
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, broker=broker)
        await trader.start()

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

    async def execute(self, trade: TradeEvent) -> str | None:
        self.trades.append(trade)
        return None

    async def get_positions(self) -> dict[str, int]:
        return {}

    async def get_cash(self) -> float:
        return 100000.0


# --- Trade confirmation & orders tests ---

@pytest.fixture
def _mock_log_order():
    """Provide a mock log_order callable for TradeExecutor."""
    mock = AsyncMock()
    return mock


class TestTradeExecution:
    @pytest.fixture
    def setup_with_mock(self):
        bus = LocalEventBus()
        broker = MockBroker()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, broker=broker)
        return bus, trader, broker

    @pytest.fixture
    def setup_with_rejecting(self):
        bus = LocalEventBus()
        broker = RejectingBroker()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, broker=broker)
        return bus, trader, broker

    @pytest.mark.asyncio
    async def test_buy_writes_order(self, setup_with_mock, _mock_log_order):
        """Trader calls log_order when broker confirms."""
        bus, trader, broker = setup_with_mock
        trader._log_order = _mock_log_order
        await bus.start()
        await trader.start()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        _mock_log_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_buy_rejected_logs_failed_order(self, setup_with_rejecting, _mock_log_order):
        """Trader logs failed order when broker rejects."""
        bus, trader, broker = setup_with_rejecting
        trader._log_order = _mock_log_order
        await bus.start()
        await trader.start()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        _mock_log_order.assert_called_once()
        call_kwargs = _mock_log_order.call_args[1]
        assert call_kwargs["status"] == "failed"
        assert call_kwargs["error"] == "broker returned None"
        assert _mock_log_order.call_args[0][1] is None  # order_id is None

    @pytest.mark.asyncio
    async def test_ttl_dedup_blocks_duplicate_orders(self, setup_with_mock):
        """TTL-based dedup in SentimentTrader prevents duplicate sends."""
        bus, trader, broker = setup_with_mock
        trades_published = []
        await bus.subscribe(CHANNEL_TRADE, lambda msg: trades_published.append(msg))
        await bus.start()
        await trader.start()

        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.1)

        # Second event for same symbol — should be skipped by TTL
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.1)

        # Still only one trade published (TTL dedup, not pending dict)
        assert len(trades_published) == 1


# --- Position store integration with trader ---

class TestTraderReadsPositionStore:
    """SentimentTrader reads from PositionStore each cycle, not on init."""

    @pytest.mark.asyncio
    async def test_reads_positions_on_each_sentiment_event(self):
        """Trader reads from PositionStore when processing sentiment, not at init."""
        mock_store = MagicMock()
        now = utcnow()
        mock_store.get_positions_with_prices.return_value = {
            "AAPL": {"entryTime": now, "entryPrice": 150.0, "qty": 10},
            "NVDA": {"entryTime": now, "entryPrice": 800.0, "qty": 5},
        }

        bus = LocalEventBus()
        await bus.start()
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, position_store=mock_store)
        broker = MockBroker()
        trader.broker = broker
        await trader.start()

        # No holdings are tracked on trader — verify by checking the store
        mock_store.get_positions_with_prices.assert_not_called()

        # On first sentiment event, trader reads from store
        sentiment = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment.to_dict())
        await asyncio.sleep(0.2)

        # Should buy more AAPL (average in) — bullish sentiment with high confidence
        assert len(broker.trades) == 1
        assert broker.trades[0].action == "buy"
        mock_store.get_positions_with_prices.assert_called()


class TestSequentialProcessing:
    """Verify that sentiment events are processed sequentially, not concurrently."""

    @pytest.mark.asyncio
    async def test_concurrent_events_use_fresh_cash(self):
        """Two rapid sentiment events should each see updated cash after the first trade."""
        bus = LocalEventBus()
        await bus.start()

        broker = MockBroker(initial_cash=20000)
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, broker=broker)
        await trader.start()

        sentiment_aapl = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        sentiment_msft = SentimentEvent(
            source="test", headline="Microsoft surges", timestamp="2026-04-22T10:00:01Z",
            analyzed_at="2026-04-22T10:00:02Z", symbols=["MSFT"],
            sentiment=0.8, confidence=0.9,
        )

        # Publish both rapidly — second should see cash reduced by first trade
        await bus.publish(CHANNEL_SENTIMENT, sentiment_aapl.to_dict())
        await bus.publish(CHANNEL_SENTIMENT, sentiment_msft.to_dict())
        await asyncio.sleep(0.5)

        assert len(broker.trades) == 2
        # Both should have executed
        symbols = {t.symbol for t in broker.trades}
        assert symbols == {"AAPL", "MSFT"}
        # Cash should be depleted by both trades (no negative balance)
        assert broker._cash >= 0

    @pytest.mark.asyncio
    async def test_second_event_sees_reduced_cash(self):
        """After first buy, second event should calculate fewer shares based on reduced cash."""
        bus = LocalEventBus()
        await bus.start()

        broker = MockBroker(initial_cash=10000)
        trader = SentimentTrader(bus, threshold=0.3, min_confidence=0.2, broker=broker)
        await trader.start()

        # First event: buy AAPL with full cash
        sentiment1 = SentimentEvent(
            source="test", headline="Apple surges", timestamp="2026-04-22T10:00:00Z",
            analyzed_at="2026-04-22T10:00:01Z", symbols=["AAPL"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment1.to_dict())
        await asyncio.sleep(0.3)

        first_cash_after = broker._cash
        assert first_cash_after < 10000, "First trade should have deducted cash"

        # Second event: buy MSFT with reduced cash
        sentiment2 = SentimentEvent(
            source="test", headline="Microsoft surges", timestamp="2026-04-22T10:00:01Z",
            analyzed_at="2026-04-22T10:00:02Z", symbols=["MSFT"],
            sentiment=0.8, confidence=0.9,
        )
        await bus.publish(CHANNEL_SENTIMENT, sentiment2.to_dict())
        await asyncio.sleep(0.3)

        assert len(broker.trades) == 2
        assert broker._cash >= 0, "Cash should never go negative"
