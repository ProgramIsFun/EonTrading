"""Event bus: publish/subscribe for signals between components."""
import asyncio
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Callable, Any


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
            asyncio.create_task(handler(message))

    async def subscribe(self, channel: str, handler: Callable):
        self._subscribers[channel].append(handler)

    async def start(self):
        pass

    async def stop(self):
        self._subscribers.clear()


class RedisEventBus(EventBus):
    """Redis-backed event bus. Works across processes and machines."""

    def __init__(self, host: str = "192.168.0.38", port: int = 6379):
        self._host = host
        self._port = port
        self._subscribers: dict[str, list[Callable]] = defaultdict(list)
        self._pubsub = None
        self._redis = None
        self._listener_task = None

    async def start(self):
        import redis.asyncio as aioredis
        self._redis = aioredis.Redis(host=self._host, port=self._port, decode_responses=True)
        self._pubsub = self._redis.pubsub()
        # Subscribe to all registered channels
        for channel in self._subscribers:
            await self._pubsub.subscribe(channel)
        self._listener_task = asyncio.create_task(self._listen())

    async def stop(self):
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()

    async def publish(self, channel: str, message: dict):
        await self._redis.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str, handler: Callable):
        self._subscribers[channel].append(handler)
        if self._pubsub:
            await self._pubsub.subscribe(channel)

    async def _listen(self):
        try:
            async for msg in self._pubsub.listen():
                if msg["type"] == "message":
                    channel = msg["channel"]
                    data = json.loads(msg["data"])
                    for handler in self._subscribers.get(channel, []):
                        asyncio.create_task(handler(data))
        except asyncio.CancelledError:
            pass
