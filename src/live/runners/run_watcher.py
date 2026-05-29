"""Run NewsWatcher as its own process. Publishes to [news] channel."""
import asyncio
import logging
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from src.common.log_handler import maybe_enable_mongo_logging
maybe_enable_mongo_logging()

from src.common.event_bus import RedisStreamBus
from src.common.heartbeat import Heartbeat
from src.common.shutdown import create_shutdown_event
from src.common.startup import banner
from src.data.news.loader import build_news_sources
from src.live.news_watcher import NewsWatcher
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

    banner("NewsWatcher", {
        "Publishes to": ", ".join(mode_parts) or "nowhere (dry run)",
        "Sources": ", ".join(source_names),
    })

    bus = RedisStreamBus(group="watcher")
    await bus.start()

    watcher = NewsWatcher(bus, sources=sources, interval_sec=120,
                          persist_news=persist,
                          publish=publish)
    logger.info("🟢 Started. Polling every 120s.")
    Heartbeat.create_background("watcher", metadata={"sources": ", ".join(source_names), "mode": "distributed"})

    watcher_task = asyncio.create_task(watcher.run())
    await create_shutdown_event().wait()
    logger.info("Shutting down...")
    watcher_task.cancel()
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
