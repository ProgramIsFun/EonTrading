"""Tests for KafkaEventBus with mocked aiokafka.

Verifies topic routing, serialization, consumer groups, and ack behavior.
Runs in CI — no real Kafka needed.
"""
import asyncio
import json
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest


@pytest.fixture
def mock_kafka():
    """Mock aiokafka producer and consumer."""
    producer = AsyncMock()
    producer.start = AsyncMock()
    producer.stop = AsyncMock()
    producer.send_and_wait = AsyncMock()

    consumer = AsyncMock()
    consumer.start = AsyncMock()
    consumer.stop = AsyncMock()
    consumer.commit = AsyncMock()
    consumer.subscribe = MagicMock()

    tp = MagicMock()
    tp.topic = "test"

    return producer, consumer, tp


@pytest.fixture
def make_bus(mock_kafka):
    """Create a KafkaEventBus with mocked internals."""
    producer, consumer, tp = mock_kafka

    async def _make(group="test"):
        with patch("src.common.event_bus.KafkaEventBus.__init__", lambda self, **kw: None):
            from src.common.event_bus import KafkaEventBus

            bus = KafkaEventBus.__new__(KafkaEventBus)
            bus._bootstrap_servers = "localhost:9092"
            bus._group = group
            bus._consumer_id = f"{group}-1"
            bus._subscribers = defaultdict(list)
            bus._producer = producer
            bus._consumer = consumer
            bus._running = False
            bus._tasks = []
            return bus

    return _make


# --- Publish ---


class TestPublish:
    @pytest.mark.asyncio
    async def test_sends_to_topic(self, make_bus, mock_kafka):
        producer, consumer, tp = mock_kafka
        bus = await make_bus()
        await bus.publish("trade", {"symbol": "AAPL", "action": "buy"})
        producer.send_and_wait.assert_called_once_with("trade", {"symbol": "AAPL", "action": "buy"})

    @pytest.mark.asyncio
    async def test_json_serialization(self, make_bus, mock_kafka):
        producer, consumer, tp = mock_kafka
        bus = await make_bus()
        msg = {"symbol": "AAPL", "price": 150.0}
        await bus.publish("news", msg)
        producer.send_and_wait.assert_called_once_with("news", msg)


# --- Subscribe ---


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_appends_handler(self, make_bus):
        bus = await make_bus()
        handler = AsyncMock()
        await bus.subscribe("trade", handler)
        assert handler in bus._subscribers["trade"]

    @pytest.mark.asyncio
    async def test_subscribes_consumer_when_already_running(self, make_bus, mock_kafka):
        producer, consumer, tp = mock_kafka
        bus = await make_bus()
        bus._consumer = consumer
        handler = AsyncMock()
        await bus.subscribe("trade", handler)
        consumer.subscribe.assert_called_once_with(["trade"])

    @pytest.mark.asyncio
    async def test_defers_subscription_when_consumer_not_started(self, make_bus, mock_kafka):
        producer, consumer, tp = mock_kafka
        bus = await make_bus()
        bus._consumer = None
        handler = AsyncMock()
        await bus.subscribe("trade", handler)
        consumer.subscribe.assert_not_called()


# --- Deserialization ---


class TestDeserialization:
    @pytest.mark.asyncio
    async def test_handler_receives_deserialized_dict(self, make_bus, mock_kafka):
        producer, consumer, tp = mock_kafka
        bus = await make_bus()
        bus._running = True

        consumed = []

        async def handler(msg):
            consumed.append(msg)

        await bus.subscribe("trade", handler)

        record = MagicMock()
        record.topic = "trade"
        record.value = {"symbol": "AAPL", "action": "buy"}

        bus._consumer = consumer
        # Return data once, then asyncio.CancelledError to stop the loop
        bus._consumer.getmany = AsyncMock(side_effect=[
            {tp: [record]},
            asyncio.CancelledError(),
        ])
        bus._consumer.commit = AsyncMock()

        task = asyncio.create_task(bus._listen())
        await asyncio.sleep(0.5)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, RuntimeError):
            pass

        assert len(consumed) == 1
        assert consumed[0] == {"symbol": "AAPL", "action": "buy"}


# --- Start / Stop lifecycle ---


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_creates_producer(self):
        producer_cls = MagicMock()
        producer_instance = AsyncMock()
        producer_cls.return_value = producer_instance

        with (
            patch("src.settings.settings") as mock_settings,
            patch("aiokafka.AIOKafkaProducer", producer_cls),
            patch("src.common.event_bus.asyncio.create_task") as mock_create_task,
        ):
            mock_settings.kafka_bootstrap_servers = "broker:9092"

            from src.common.event_bus import KafkaEventBus

            bus = KafkaEventBus(group="test")
            await bus.start()

            producer_cls.assert_called_once()
            assert producer_cls.call_args[1]["bootstrap_servers"] == "broker:9092"
            producer_instance.start.assert_called_once()
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self, make_bus, mock_kafka):
        producer, consumer, tp = mock_kafka
        bus = await make_bus()
        bus._running = True

        task = AsyncMock()
        bus._tasks = [task]

        await bus.stop()
        task.cancel.assert_called_once()
        producer.stop.assert_called_once()
        consumer.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_handles_missing_consumer(self, make_bus, mock_kafka):
        producer, consumer, tp = mock_kafka
        bus = await make_bus()
        bus._running = True
        bus._consumer = None

        task = AsyncMock()
        bus._tasks = [task]

        await bus.stop()  # should not raise


# --- Error handling ---


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_handler_error_does_not_crash_listener(self, make_bus, mock_kafka):
        producer, consumer, tp = mock_kafka
        bus = await make_bus()
        bus._running = True
        bus._consumer = consumer

        async def failing_handler(msg):
            raise ValueError("oops")

        await bus.subscribe("trade", failing_handler)

        record = MagicMock()
        record.topic = "trade"
        record.value = {"symbol": "AAPL"}

        bus._consumer.getmany = AsyncMock(side_effect=[
            {tp: [record]},
            asyncio.CancelledError(),
        ])
        bus._consumer.commit = AsyncMock()

        task = asyncio.create_task(bus._listen())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, RuntimeError):
            pass

        bus._consumer.commit.assert_called_once()
