"""Run AnalyzerService as its own process. Subscribes to [news], publishes to [sentiment]."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging("analyzer")
logger = logging.getLogger(__name__)

from src.common.factories import build_analyzer
from src.common.position_store import PositionStore
from src.common.shutdown import create_shutdown_event
from src.live.analyzer_service import AnalyzerService
from src.live.runners import runner_lifecycle


async def main():
    analyzer, analyzer_name = build_analyzer()

    async with runner_lifecycle("analyzer", "AnalyzerService", {
        "Subscribes to": "[news]",
        "Publishes to": "[sentiment]",
        "Analyzer": analyzer_name,
        "Positions from": "MongoDB",
    }) as bus:
        logger.info("Analyzer mode: %s", analyzer_name)
        store = PositionStore()
        svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
        await svc.start()
        logger.info("🟢 Started. Waiting for [news] events.")
        await create_shutdown_event().wait()

if __name__ == "__main__":
    asyncio.run(main())
