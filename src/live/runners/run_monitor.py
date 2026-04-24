"""Run PriceMonitor as its own process. Watches positions, triggers SL/TP via [trade]."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
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

    redis_host = os.getenv("REDIS_HOST", "192.168.0.38")
    bus = RedisEventBus(host=redis_host)
    await bus.start()

    store = PositionStore()
    logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
    monitor = PriceMonitor(bus, store, logic, interval_sec=60)

    asyncio.ensure_future(Heartbeat("monitor", metadata={"mode": "distributed"}).run())
    ping = PingResponder(bus, ["monitor"], metadata={"monitor": {"mode": "distributed"}})
    await ping.start()

    print(f"  🟢 Started. Checking prices every 60s.\n")
    await monitor.run()

if __name__ == "__main__":
    asyncio.run(main())
