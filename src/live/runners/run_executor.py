"""Run TradeExecutor as its own process. Subscribes to [trade], executes via broker."""
import asyncio, os
from dotenv import load_dotenv
load_dotenv()

from src.common.event_bus import RedisEventBus
from src.live.brokers.broker import TradeExecutor, LogBroker, FutuBroker, IBKRBroker, AlpacaBroker


async def main():
    bus = RedisEventBus(host=os.getenv("REDIS_HOST", "192.168.0.38"))
    await bus.subscribe("trade", lambda _: None)
    await bus.start()

    broker_name = os.getenv("BROKER", "log").lower()
    if broker_name == "futu":
        broker = FutuBroker(simulate=not os.getenv("FUTU_REAL"))
    elif broker_name == "ibkr":
        broker = IBKRBroker()
    elif broker_name == "alpaca":
        broker = AlpacaBroker()
    else:
        broker = LogBroker()

    executor = TradeExecutor(bus, broker)
    await executor.start()
    print(f"TradeExecutor process started (broker: {broker.__class__.__name__})")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
