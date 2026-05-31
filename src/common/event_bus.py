"""Event bus: publish/subscribe for signals between components.

Implementations:
  - LocalEventBus: in-memory, single process
  - RedisStreamBus: Redis Streams (persistent message queue)
  - KafkaEventBus: Apache Kafka (distributed message queue)
"""
import asyncio
import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Callable

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


class RedisStreamBus(EventBus):
    """Redis Streams for persistent message queues.

    Each subscriber group gets its own consumer group on the stream.
    Messages survive container restarts — consumers pick up where they left off.
    """

    def __init__(self, host: str = None, port: int = None, group: str = "default"):
        from src.settings import settings
        self._host = host or settings.redis_host
        self._port = port or settings.redis_port
        self._group = group
        self._consumer = f"{group}-{id(self)}"
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._redis = None
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        import redis.asyncio as aioredis
        self._redis = aioredis.Redis(host=self._host, port=self._port, decode_responses=True)

        try:
            await self._redis.ping()
        except Exception as e:
            raise ConnectionError(f"Redis not reachable at {self._host}:{self._port} — {e}") from e

        for channel in self._subscribers:
            await self._ensure_group(channel)

        self._tasks.append(asyncio.create_task(self._listen_streams()))

    async def stop(self):
        for task in self._tasks:
            task.cancel()
        if self._redis:
            await self._redis.aclose()

    async def publish(self, channel: str, message: dict):
        await self._redis.xadd(f"stream:{channel}", {"data": json.dumps(message)})

    async def subscribe(self, channel: str, handler: Callable):
        self._subscribers[channel].append(handler)
        if self._redis:
            await self._ensure_group(channel)

    async def _ensure_group(self, channel: str):
        """Create consumer group if it doesn't exist."""
        try:
            await self._redis.xgroup_create(f"stream:{channel}", self._group, id="0", mkstream=True)
        except Exception:
            pass  # group already exists — expected

    async def _listen_streams(self):
        """Read from Redis Streams with consumer groups — persistent, at-least-once."""
        try:
            while True:
                streams = {f"stream:{ch}": ">" for ch in self._subscribers}
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


class KafkaEventBus(EventBus):
    """Apache Kafka-backed event bus for distributed mode.

    Each channel maps to a Kafka topic.
    Each subscriber group creates its own consumer group — messages are
    load-balanced across consumers in the same group.
    """

    def __init__(self, bootstrap_servers: str = None, group: str = "default"):
        from src.settings import settings
        self._bootstrap_servers = bootstrap_servers or settings.kafka_bootstrap_servers
        self._group = group
        self._consumer_id = f"{group}-{id(self)}"
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._producer = None
        self._consumer = None
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        from aiokafka import AIOKafkaProducer
        self._running = True
        self._producer = AIOKafkaProducer(
            bootstrap_servers=self._bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode(),
        )
        await self._producer.start()
        self._tasks.append(asyncio.create_task(self._listen()))

    async def stop(self):
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._producer:
            await self._producer.stop()
        if self._consumer:
            await self._consumer.stop()

    async def publish(self, channel: str, message: dict):
        await self._producer.send_and_wait(channel, message)

    async def subscribe(self, channel: str, handler: Callable):
        self._subscribers[channel].append(handler)
        if self._consumer is not None:
            self._consumer.subscribe(list(self._subscribers.keys()))

    async def _listen(self):
        from aiokafka import AIOKafkaConsumer

        try:
            while self._running:
                topics = list(self._subscribers.keys())
                if not topics:
                    await asyncio.sleep(0.5)
                    continue

                if self._consumer is None:
                    self._consumer = AIOKafkaConsumer(
                        *topics,
                        bootstrap_servers=self._bootstrap_servers,
                        group_id=self._group,
                        value_deserializer=lambda v: json.loads(v.decode()),
                        auto_offset_reset="earliest",
                        enable_auto_commit=False,
                    )
                    await self._consumer.start()
                    continue

                try:
                    msgs = await asyncio.wait_for(
                        self._consumer.getmany(timeout_ms=1000, max_records=50),
                        timeout=1.5,
                    )
                except asyncio.TimeoutError:
                    continue

                for tp, records in msgs.items():
                    for msg in records:
                        for handler in self._subscribers.get(msg.topic, []):
                            try:
                                await handler(msg.value)
                            except Exception:
                                logger.error("Handler error on %s", msg.topic, exc_info=True)
                if msgs:
                    await self._consumer.commit()
        except asyncio.CancelledError:
            pass


def _log_task_exception(task: asyncio.Task):
    """Callback to log exceptions from fire-and-forget tasks."""
    if not task.cancelled() and task.exception():
        logger.error("Unhandled exception in event handler: %s", task.exception(), exc_info=task.exception())
