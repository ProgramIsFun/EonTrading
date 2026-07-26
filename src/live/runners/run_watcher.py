"""Run NewsWatcher as its own process. Publishes to [news] channel."""
import asyncio
import logging

from src.common.log_handler import setup_logging
setup_logging("newswatcher")
logger = logging.getLogger(__name__)

from src.common.shutdown import create_shutdown_event
from src.data.news.loader import build_news_sources
from src.live.news_watcher import NewsWatcher
from src.live.runners import runner_lifecycle
from src.settings import settings


async def main():
    sources, source_names = build_news_sources()
    persist = settings.persist_news
    publish = settings.publish_pipeline

    mode_parts = []
    if publish:
        mode_parts.append("pipeline [news]")
    if persist:
        mode_parts.append("MongoDB")

    async with runner_lifecycle("newswatcher", "NewsWatcher", {
        "Publishes to": ", ".join(mode_parts) or "nowhere (dry run)",
        "Sources": ", ".join(source_names),
    }) as bus:
        watcher = NewsWatcher(bus, sources=sources, interval_sec=120,
                              persist_news=persist,
                              publish=publish)
        logger.info("🟢 Started. Polling every 120s.")
        watcher_task = asyncio.create_task(watcher.run())
        await create_shutdown_event().wait()
        watcher_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())
