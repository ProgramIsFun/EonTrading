"""Run AnalyzerService as its own process. Subscribes to [news], publishes to [sentiment]."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

from src.common.event_bus import RedisStreamBus
from src.common.factories import build_analyzer
from src.common.heartbeat import Heartbeat
from src.common.position_store import PositionStore
from src.common.shutdown import create_shutdown_event
from src.common.startup import banner
from src.live.analyzer_service import AnalyzerService


async def main():
    analyzer, analyzer_name = build_analyzer()

    banner("AnalyzerService", {
        "Subscribes to": "[news]",
        "Publishes to": "[sentiment]",
        "Analyzer": analyzer_name,
        "Positions from": "MongoDB",
    })

    bus = RedisStreamBus(group="analyzer")
    await bus.start()

    store = PositionStore()
    svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    await svc.start()
    logger.info("🟢 Started. Waiting for [news] events.")
    Heartbeat.create_background("analyzer", metadata={"analyzer": analyzer_name, "mode": "distributed"})
    await create_shutdown_event().wait()
    logger.info("Shutting down...")
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
