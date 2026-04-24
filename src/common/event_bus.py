"""Event bus: publish/subscribe for signals between components.

Implementations:
  - LocalEventBus: in-memory, single process
  - RedisStreamBus: Redis Streams (persistent message queue) + Pub/Sub for broadcast
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Callable, Any

logger = logging.getLogger(__name__)


class EventBus(ABC):
    @abstractmethod
    async def publish(self, channel: str, message: dict):
        pass

    @abstractmethod
    async def subscribe(self, channel: str, handler: Callable):
        """handler is an async function: async def handler(message: dict)"""
        pass

    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass


class LocalEventBus(EventBus):
    """In-process event bus using asyncio. Multiple subscribers supported."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)

    async def publish(self, channel: str, message: dict):
        for handler in self._subscribers.get(channel, []):
            task = asyncio.create_task(handler(message))
            task.add_done_callback(_log_task_exception)

    async def subscribe(self, channel: str, handler: Callable):
        self._subscribers[channel].append(handler)

    async def start(self):
        pass

    async def stop(self):
        self._subscribers.clear()


# Channels that use pub/sub (broadcast) instead of streams (queue)
_PUBSUB_CHANNELS = {"ping", "pong"}


class RedisStreamBus(EventBus):
    """Redis Streams for pipeline channels (persistent message queue).
    Redis Pub/Sub for ephemeral broadcast channels (ping/pong).

    Each subscriber group gets its own consumer group on the stream.
    Messages survive container restarts — consumers pick up where they left off.
    """

    def __init__(self, host: str = None, port: int = None, group: str = "default"):
        from src.env import REDIS_HOST, REDIS_PORT
        self._host = host or REDIS_HOST
        self._port = port or REDIS_PORT
        self._group = group
        self._consumer = f"{group}-{id(self)}"
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._redis = None
        self._pubsub = None
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        import redis.asyncio as aioredis
        self._redis = aioredis.Redis(host=self._host, port=self._port, decode_responses=True)

        # Create consumer groups for any pre-registered stream channels
        for channel in self._subscribers:
            if channel not in _PUBSUB_CHANNELS:
                await self._ensure_group(channel)

        # Start single listener that handles both streams and pub/sub dynamically
        self._tasks.append(asyncio.create_task(self._listen_streams()))
        self._tasks.append(asyncio.create_task(self._listen_pubsub()))

    async def stop(self):
        for task in self._tasks:
            task.cancel()
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.aclose()
        if self._redis:
            await self._redis.aclose()

    async def publish(self, channel: str, message: dict):
        if channel in _PUBSUB_CHANNELS:
            await self._redis.publish(channel, json.dumps(message))
        else:
            await self._redis.xadd(f"stream:{channel}", {"data": json.dumps(message)})

    async def subscribe(self, channel: str, handler: Callable):
        self._subscribers[channel].append(handler)
        if self._redis and channel not in _PUBSUB_CHANNELS:
            await self._ensure_group(channel)
        if self._redis and channel in _PUBSUB_CHANNELS and self._pubsub:
            await self._pubsub.subscribe(channel)

    async def _ensure_group(self, channel: str):
        """Create consumer group if it doesn't exist."""
        try:
            await self._redis.xgroup_create(f"stream:{channel}", self._group, id="0", mkstream=True)
        except Exception:
            pass  # group already exists

    async def _listen_streams(self):
        """Read from Redis Streams with consumer groups — persistent, at-least-once."""
        try:
            while True:
                # Dynamically build stream list from current subscribers
                streams = {}
                for ch in self._subscribers:
                    if ch not in _PUBSUB_CHANNELS:
                        streams[f"stream:{ch}"] = ">"
                if not streams:
                    await asyncio.sleep(0.5)
                    continue

                results = await self._redis.xreadgroup(
                    self._group, self._consumer, streams, count=10, block=1000,
                )
                for stream_key, messages in results:
                    channel = stream_key.replace("stream:", "", 1)
                    for msg_id, fields in messages:
                        data = json.loads(fields["data"])
                        for handler in self._subscribers.get(channel, []):
                            try:
                                await handler(data)
                            except Exception:
                                logger.error("Handler error on %s", channel, exc_info=True)
                        await self._redis.xack(f"stream:{channel}", self._group, msg_id)
        except asyncio.CancelledError:
            pass

    async def _listen_pubsub(self):
        """Read from Redis Pub/Sub — ephemeral broadcast (ping/pong)."""
        self._pubsub = self._redis.pubsub()
        # Subscribe to any pre-registered pubsub channels
        for ch in self._subscribers:
            if ch in _PUBSUB_CHANNELS:
                await self._pubsub.subscribe(ch)
        try:
            async for msg in self._pubsub.listen():
                if msg["type"] == "message":
                    channel = msg["channel"]
                    data = json.loads(msg["data"])
                    for handler in self._subscribers.get(channel, []):
                        task = asyncio.create_task(handler(data))
                        task.add_done_callback(_log_task_exception)
        except asyncio.CancelledError:
            pass


def _log_task_exception(task: asyncio.Task):
    """Callback to log exceptions from fire-and-forget tasks."""
    if not task.cancelled() and task.exception():
        logger.error("Unhandled exception in event handler: %s", task.exception(), exc_info=task.exception())
