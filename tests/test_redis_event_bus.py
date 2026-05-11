"""Tests for RedisStreamBus with mocked Redis client.

Verifies stream/pubsub routing, serialization, consumer groups, and ack behavior.
Runs in CI — no real Redis needed.
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Mock redis.asyncio.Redis client."""
    r = AsyncMock()
    r.xadd = AsyncMock()
    r.xreadgroup = AsyncMock(return_value=[])
    r.xack = AsyncMock()
    r.xgroup_create = AsyncMock()
    r.publish = AsyncMock()
    r.close = AsyncMock()

    # Mock pubsub
    ps = AsyncMock()
    ps.subscribe = AsyncMock()
    ps.unsubscribe = AsyncMock()
    ps.close = AsyncMock()

    async def _empty_listen():
        while True:
            await asyncio.sleep(10)
            yield  # never yields, just blocks

    ps.listen = _empty_listen
    r.pubsub = MagicMock(return_value=ps)

    return r, ps


@pytest.fixture
def make_bus(mock_redis):
    """Create a RedisStreamBus with mocked Redis."""
    r, ps = mock_redis

    async def _make(group="test"):
        with patch("src.common.event_bus.RedisStreamBus.__init__", lambda self, **kw: None):
            from src.common.event_bus import RedisStreamBus
            bus = RedisStreamBus.__new__(RedisStreamBus)
            from collections import defaultdict
            bus._host = "localhost"
            bus._port = 6379
            bus._group = group
            bus._consumer = f"{group}-1"
            bus._subscribers = defaultdict(list)
            bus._redis = r
            bus._pubsub = None
            bus._tasks = []
            return bus

    return _make


# --- Publish routing ---

class TestPublishRouting:

    @pytest.mark.asyncio
    async def test_pipeline_channel_uses_xadd(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus()

        await bus.publish("trade", {"symbol": "AAPL", "action": "buy"})

        r.xadd.assert_called_once()
        call_args = r.xadd.call_args
        assert call_args[0][0] == "stream:trade"
        payload = json.loads(call_args[0][1]["data"])
        assert payload["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_ping_channel_uses_pubsub(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus()

        await bus.publish("ping", {"ts": "2026-01-01"})

        r.publish.assert_called_once()
        assert r.publish.call_args[0][0] == "ping"
        r.xadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_pong_channel_uses_pubsub(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus()

        await bus.publish("pong", {"component": "watcher"})

        r.publish.assert_called_once()
        assert r.publish.call_args[0][0] == "pong"

    @pytest.mark.asyncio
    async def test_all_pipeline_channels_use_streams(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus()

        for ch in ["news", "sentiment", "trade", "fill"]:
            r.xadd.reset_mock()
            await bus.publish(ch, {"test": True})
            r.xadd.assert_called_once()
            assert r.xadd.call_args[0][0] == f"stream:{ch}"


# --- Subscribe + consumer group creation ---

class TestSubscribe:

    @pytest.mark.asyncio
    async def test_subscribe_creates_consumer_group(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus(group="analyzer")

        handler = AsyncMock()
        await bus.subscribe("news", handler)

        r.xgroup_create.assert_called_once_with("stream:news", "analyzer", id="0", mkstream=True)

    @pytest.mark.asyncio
    async def test_subscribe_pubsub_channel_does_not_create_group(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus()
        bus._pubsub = ps  # simulate started state

        handler = AsyncMock()
        await bus.subscribe("ping", handler)

        r.xgroup_create.assert_not_called()
        ps.subscribe.assert_called_once_with("ping")

    @pytest.mark.asyncio
    async def test_duplicate_group_creation_is_safe(self, make_bus, mock_redis):
        r, ps = mock_redis
        r.xgroup_create.side_effect = Exception("BUSYGROUP Consumer Group name already exists")
        bus = await make_bus()

        handler = AsyncMock()
        await bus.subscribe("trade", handler)
        # Should not raise


# --- Serialization ---

class TestSerialization:

    @pytest.mark.asyncio
    async def test_message_serialized_as_json(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus()

        msg = {"symbol": "NVDA", "price": 150.5, "symbols": ["NVDA", "AAPL"]}
        await bus.publish("sentiment", msg)

        payload = json.loads(r.xadd.call_args[0][1]["data"])
        assert payload == msg

    @pytest.mark.asyncio
    async def test_pubsub_message_serialized_as_json(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus()

        msg = {"ts": "2026-01-01T00:00:00Z"}
        await bus.publish("ping", msg)

        payload = json.loads(r.publish.call_args[0][1])
        assert payload == msg


# --- Stream listener behavior ---

class TestStreamListener:

    @pytest.mark.asyncio
    async def test_listener_calls_handler_and_acks(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus(group="executor")

        received = []
        handler = AsyncMock(side_effect=lambda msg: received.append(msg))
        await bus.subscribe("trade", handler)

        # Simulate xreadgroup returning one message, then empty forever
        msg_data = json.dumps({"symbol": "AAPL", "action": "buy"})
        call_count = 0

        async def fake_xreadgroup(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [("stream:trade", [("1-0", {"data": msg_data})])]
            await asyncio.sleep(10)
            return []

        r.xreadgroup = fake_xreadgroup

        task = asyncio.create_task(bus._listen_streams())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(received) == 1
        assert received[0]["symbol"] == "AAPL"
        r.xack.assert_called_once_with("stream:trade", "executor", "1-0")

    @pytest.mark.asyncio
    async def test_listener_skips_channels_with_no_subscribers(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus()

        # No subscribers — listener should sleep and loop
        call_count = 0

        async def fake_xreadgroup(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(10)
            return []

        r.xreadgroup = fake_xreadgroup

        task = asyncio.create_task(bus._listen_streams())
        await asyncio.sleep(0.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # xreadgroup should not have been called (no streams to read)
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_handler_error_does_not_crash_listener(self, make_bus, mock_redis):
        r, ps = mock_redis
        bus = await make_bus(group="test")

        bad_handler = AsyncMock(side_effect=ValueError("boom"))
        await bus.subscribe("trade", bad_handler)

        msg_data = json.dumps({"symbol": "FAIL"})
        call_count = 0

        async def fake_xreadgroup(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [("stream:trade", [("1-0", {"data": msg_data})])]
            await asyncio.sleep(10)
            return []

        r.xreadgroup = fake_xreadgroup

        task = asyncio.create_task(bus._listen_streams())
        await asyncio.sleep(0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Handler was called despite error
        bad_handler.assert_called_once()
        # Message was still acked (at-least-once, not exactly-once)
        r.xack.assert_called_once()
