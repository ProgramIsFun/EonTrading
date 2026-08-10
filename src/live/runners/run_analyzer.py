"""Run AnalyzerService as its own process. Subscribes to [news], publishes to [sentiment]."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging("analyzer")
logger = logging.getLogger(__name__)

from src.common.factories import build_analyzer
from src.common.portfolio import build_portfolio_source
from src.common.shutdown import create_shutdown_event
from src.live.analyzer_service import AnalyzerService
from src.live.runners import runner_lifecycle
from src.settings import settings


async def main():
    analyzer, analyzer_name = build_analyzer()
    portfolio_source = build_portfolio_source()

    async with runner_lifecycle("analyzer", "AnalyzerService", {
        "Subscribes to": "[news]",
        "Publishes to": "[sentiment]",
        "Analyzer": analyzer_name,
        "Portfolio from": f"{portfolio_source.__class__.__name__} ({settings.portfolio_source})",
    }) as bus:
        logger.info("Analyzer mode: %s", analyzer_name)
        svc = AnalyzerService(bus, analyzer=analyzer, portfolio_source=portfolio_source)
        await svc.start()
        logger.info("🟢 Started. Waiting for [news] events.")
        await create_shutdown_event().wait()

if __name__ == "__main__":
    asyncio.run(main())
