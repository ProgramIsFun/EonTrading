"""Integration tests with real Redis — verifies streams, consumer groups, persistence.

Requires Redis running on localhost:6379.
Run with: PYTHONPATH=. python -m pytest tests/test_redis_live.py -v
Skip with: python -m pytest -m "not redis"
"""
import asyncio
import json

import pytest

redis_available = False
try:
    import redis as _redis
    _r = _redis.Redis(host="localhost", port=6379)
    _r.ping()
    redis_available = True
    _r.close()
except Exception:
    pass

pytestmark = pytest.mark.redis
skip_no_redis = pytest.mark.skipif(not redis_available, reason="Redis not running on localhost:6379")


def _cleanup_streams(*keys):
    """Delete test streams after test."""
    import redis
    r = redis.Redis(host="localhost", port=6379)
    for k in keys:
        r.delete(k)
    r.close()


@skip_no_redis
class TestRedisStreamsLive:

    @pytest.mark.asyncio
    async def test_publish_and_consume(self):
        """Message published to stream is received by consumer."""
        from src.common.event_bus import RedisStreamBus

        received = []

        async def handler(msg):
            received.append(msg)

        bus = RedisStreamBus(host="localhost", group="test-consume")
        await bus.subscribe("test_ch", handler)
        await bus.start()

        await bus.publish("test_ch", {"symbol": "AAPL", "action": "buy"})
        await asyncio.sleep(0.5)

        await bus.stop()
        _cleanup_streams("stream:test_ch")

        assert len(received) == 1
        assert received[0]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_messages_survive_reconnect(self):
        """Messages published while consumer is down are delivered after reconnect."""
        import redis.asyncio as aioredis

        from src.common.event_bus import RedisStreamBus

        stream_key = "stream:test_persist"
        group = "test-persist"

        # Clean up from previous runs
        _cleanup_streams(stream_key)

        # Publish directly to Redis (simulating messages sent while consumer was down)
        r = aioredis.Redis(host="localhost", port=6379, decode_responses=True)
        try:
            await r.xgroup_create(stream_key, group, id="0", mkstream=True)
        except Exception:
            pass
        await r.xadd(stream_key, {"data": json.dumps({"msg": "while-you-were-away"})})
        await r.aclose()

        # Now start consumer — should pick up the pending message
        received = []

        async def handler(msg):
            received.append(msg)

        bus = RedisStreamBus(host="localhost", group=group)
        await bus.subscribe("test_persist", handler)
        await bus.start()
        await asyncio.sleep(0.5)
        await bus.stop()

        _cleanup_streams(stream_key)

        assert len(received) == 1
        assert received[0]["msg"] == "while-you-were-away"

    @pytest.mark.asyncio
    async def test_two_consumer_groups_both_receive(self):
        """Two different consumer groups each get a copy of every message."""
        from src.common.event_bus import RedisStreamBus

        received_a = []
        received_b = []

        bus_a = RedisStreamBus(host="localhost", group="group-a")
        bus_b = RedisStreamBus(host="localhost", group="group-b")

        await bus_a.subscribe("test_multi", lambda msg: _async_append(received_a, msg))
        await bus_b.subscribe("test_multi", lambda msg: _async_append(received_b, msg))

        await bus_a.start()
        await bus_b.start()

        await bus_a.publish("test_multi", {"n": 1})
        await asyncio.sleep(0.5)

        await bus_a.stop()
        await bus_b.stop()
        _cleanup_streams("stream:test_multi")

        assert len(received_a) == 1
        assert len(received_b) == 1

    @pytest.mark.asyncio
    async def test_ping_pong_broadcast(self):
        """Ping/pong uses pub/sub — all subscribers receive the message."""
        from src.common.event_bus import RedisStreamBus

        received = []

        bus = RedisStreamBus(host="localhost", group="test-ping")
        await bus.subscribe("pong", lambda msg: _async_append(received, msg))
        await bus.start()
        await asyncio.sleep(0.2)  # let pubsub subscription register

        await bus.publish("pong", {"component": "watcher"})
        await asyncio.sleep(0.3)

        await bus.stop()

        assert len(received) == 1
        assert received[0]["component"] == "watcher"

    @pytest.mark.asyncio
    async def test_message_acked_after_processing(self):
        """After processing, message should not be re-delivered."""
        from src.common.event_bus import RedisStreamBus

        stream_key = "stream:test_ack"
        group = "test-ack"
        _cleanup_streams(stream_key)

        received = []

        async def handler(msg):
            received.append(msg)

        # First consumer — processes the message
        bus1 = RedisStreamBus(host="localhost", group=group)
        await bus1.subscribe("test_ack", handler)
        await bus1.start()
        await bus1.publish("test_ack", {"n": 1})
        await asyncio.sleep(0.5)
        await bus1.stop()

        assert len(received) == 1

        # Second consumer in same group — should NOT get the message again
        received.clear()
        bus2 = RedisStreamBus(host="localhost", group=group)
        await bus2.subscribe("test_ack", handler)
        await bus2.start()
        await asyncio.sleep(0.5)
        await bus2.stop()

        _cleanup_streams(stream_key)

        assert len(received) == 0


async def _async_append(lst, msg):
    lst.append(msg)
