"""Run AnalyzerService as its own process. Subscribes to [news], publishes to [sentiment]."""
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from src.common.event_bus import RedisStreamBus
from src.common.factories import build_analyzer
from src.common.heartbeat import Heartbeat
from src.common.ping import PingResponder
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
    asyncio.create_task(Heartbeat.create_background("analyzer", metadata={"analyzer": analyzer_name, "mode": "distributed"}))
    ping = PingResponder(bus, ["analyzer"], metadata={"analyzer": {"analyzer": analyzer_name, "mode": "distributed"}})
    await ping.start()

    await create_shutdown_event().wait()
    logger.info("Shutting down...")
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
