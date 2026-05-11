"""Ping/pong health check via event bus — real-time component status."""
import asyncio

from src.common.clock import utcnow
from src.common.event_bus import EventBus

CHANNEL_PING = "ping"
CHANNEL_PONG = "pong"


class PingResponder:
    """Listens on [ping], replies on [pong] with component name + metadata."""

    def __init__(self, bus: EventBus, components: list[str], metadata: dict = None):
        """
        components: list of component names this responder speaks for.
          - Single process: ["watcher", "analyzer", "trader", "executor"]
          - Distributed: ["watcher"] or ["analyzer"] etc.
        """
        self.bus = bus
        self.components = components
        self.metadata = metadata or {}

    async def start(self):
        await self.bus.subscribe(CHANNEL_PING, self._on_ping)

    async def _on_ping(self, msg: dict):
        for name in self.components:
            await self.bus.publish(CHANNEL_PONG, {
                "component": name,
                "timestamp": utcnow().isoformat() + "Z",
                **self.metadata.get(name, {}),
            })


async def collect_pongs(bus: EventBus, timeout: float = 1.0) -> list[dict]:
    """Publish a ping and collect pong responses for `timeout` seconds."""
    responses = []

    async def _on_pong(msg: dict):
        responses.append(msg)

    await bus.subscribe(CHANNEL_PONG, _on_pong)
    await bus.publish(CHANNEL_PING, {"ts": utcnow().isoformat()})
    await asyncio.sleep(timeout)
    return responses
