"""Run TradeExecutor as its own process. Subscribes to [trade], broker publishes to [fill]."""
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
from src.live.brokers.broker import TradeExecutor, PaperBroker, FutuBroker, IBKRBroker, AlpacaBroker


async def main():
    broker_name = os.getenv("BROKER", "log").lower()
    if broker_name == "futu":
        confirm = os.getenv("FUTU_CONFIRM", "poll")
        broker = FutuBroker(simulate=not os.getenv("FUTU_REAL"), confirm_mode=confirm)
    elif broker_name == "ibkr":
        broker = IBKRBroker()
    elif broker_name == "alpaca":
        broker = AlpacaBroker()
    else:
        broker = PaperBroker()

    required = {"futu": ["FUTU_LIVE"], "ibkr": [], "alpaca": ["ALPACA_API_KEY", "ALPACA_SECRET_KEY"]}
    missing = [v for v in required.get(broker_name, []) if not os.getenv(v)]

    banner("TradeExecutor", {
        "Subscribes to": "[trade]",
        "Publishes to": "[fill]",
        "Broker": broker.__class__.__name__,
        "Missing env vars": ", ".join(missing) if missing else "none",
        "Redis": os.getenv("REDIS_HOST", "localhost"),
    })

    if missing:
        logger.warning("Missing env vars: %s — broker may fail", ", ".join(missing))

    bus = RedisStreamBus(group="executor")
    await bus.start()

    executor = TradeExecutor(bus, broker)
    await executor.start()
    logger.info("🟢 Started. Waiting for [trade] events.")
    asyncio.create_task(Heartbeat("executor", metadata={"broker": broker.__class__.__name__, "mode": "distributed"}).run())
    ping = PingResponder(bus, ["executor"], metadata={"executor": {"broker": broker.__class__.__name__, "mode": "distributed"}})
    await ping.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    await stop_event.wait()
    logger.info("Shutting down...")
    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())
