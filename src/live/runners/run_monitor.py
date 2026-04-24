"""Run PriceMonitor as its own process. Watches positions, triggers SL/TP via [trade]."""
import asyncio, logging, os, signal
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

from src.common.event_bus import RedisStreamBus
from src.common.startup import banner
from src.common.heartbeat import Heartbeat
from src.common.ping import PingResponder
from src.common.position_store import PositionStore
from src.common.trading_logic import TradingLogic
from src.live.price_monitor import PriceMonitor


async def main():
    banner("PriceMonitor", {
        "Publishes to": "[trade]",
        "Reads from": "MongoDB positions",
        "SL": "5%",
        "TP": "10%",
        "Interval": "60s",
        "Redis": os.getenv("REDIS_HOST", "localhost"),
    })

    bus = RedisStreamBus(group="monitor")
    await bus.start()

    store = PositionStore()
    logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
    monitor = PriceMonitor(bus, store, logic, interval_sec=60)

    asyncio.create_task(Heartbeat("monitor", metadata={"mode": "distributed"}).run())
    ping = PingResponder(bus, ["monitor"], metadata={"monitor": {"mode": "distributed"}})
    await ping.start()

    logger.info("🟢 Started. Checking prices every 60s.")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    monitor_task = asyncio.create_task(monitor.run())
    await stop_event.wait()
    logger.info("Shutting down...")
    monitor_task.cancel()
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
