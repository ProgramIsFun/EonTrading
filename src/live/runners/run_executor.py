"""Run TradeExecutor as its own process. Subscribes to [trade], broker publishes to [fill]."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
from src.common.startup import banner
from src.common.heartbeat import Heartbeat
from src.common.ping import PingResponder
from src.live.brokers.broker import TradeExecutor, LogBroker, FutuBroker, IBKRBroker, AlpacaBroker


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
        broker = LogBroker()

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
        print(f"  ⚠️  Warning: {', '.join(missing)} not set — broker may fail\n")

    bus = RedisEventBus(host=os.getenv("REDIS_HOST", "192.168.0.38"))
    await bus.subscribe("trade", lambda _: None)
    await bus.start()

    executor = TradeExecutor(bus, broker)
    await executor.start()
    print(f"  🟢 Started. Waiting for [trade] events.\n")
    asyncio.ensure_future(Heartbeat("executor", metadata={"broker": broker.__class__.__name__, "mode": "distributed"}).run())
    ping = PingResponder(bus, ["executor"], metadata={"executor": {"broker": broker.__class__.__name__, "mode": "distributed"}})
    await ping.start()
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
