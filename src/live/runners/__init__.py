"""Shared runner lifecycle for all distributed-mode entry points."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.common.event_bus import RedisStreamBus

logger = logging.getLogger(__name__)


@asynccontextmanager
async def runner_lifecycle(
    name: str,
    banner_title: str,
    banner_info: dict[str, str],
    heartbeat_metadata: dict[str, str] | None = None,
) -> AsyncIterator[RedisStreamBus]:
    """Common lifecycle shared by every runner.

    Yields the started RedisStreamBus.  On exit the bus is stopped.
    The caller is responsible for creating components and waiting for
    ``create_shutdown_event().wait()`` inside the context.
    """
    from src.common.event_bus import RedisStreamBus
    from src.common.heartbeat import Heartbeat
    from src.common.startup import banner

    banner(banner_title, banner_info)

    bus = RedisStreamBus(group=name)
    await bus.start()

    Heartbeat.create_background(
        name, metadata=heartbeat_metadata or {"mode": "distributed"}
    )

    try:
        yield bus
    finally:
        logger.info("Shutting down...")
        await bus.stop()
