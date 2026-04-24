"""Distributed replay — feeds historical news through the distributed pipeline via Redis.

Usage:
  1. Start distributed containers: docker compose --profile distributed up -d
     (make sure BROKER=log for safety)
  2. Run this controller:
     REDIS_HOST=localhost PYTHONPATH=. python -m src.live.replay_distributed --start 2025-01-01 --end 2025-06-01

Timestamps flow with the events — no clock sync needed.
Each component uses the event's timestamp for price lookups.
"""
import asyncio
import argparse
import os
from dotenv import load_dotenv
load_dotenv()

from src.common.sample_news import SAMPLE_NEWS


async def main(start: str, end: str):
    from src.common.event_bus import RedisEventBus
    from src.common.events import CHANNEL_NEWS, NewsEvent

    redis_host = os.getenv("REDIS_HOST", "localhost")
    bus = RedisEventBus(host=redis_host, group="replay")
    await bus.start()

    fills = []
    async def on_fill(msg):
        fills.append(msg)
    await bus.subscribe("fill", on_fill)

    print(f"\n{'═' * 60}")
    print(f"  Distributed Replay Controller")
    print(f"  Redis: {redis_host}")
    print(f"  News events: {len(SAMPLE_NEWS)}")
    print(f"  ⚠️  Make sure BROKER=log in executor container!")
    print(f"{'═' * 60}\n")

    for doc in SAMPLE_NEWS:
        print(f"  📅 {doc['date']} — {doc['headline'][:65]}")

        event = NewsEvent(
            source="replay",
            headline=doc["headline"],
            timestamp=doc["date"],
            url="",
            body=doc["headline"],
        )
        await bus.publish(CHANNEL_NEWS, event.to_dict())

        prev_fills = len(fills)
        await asyncio.sleep(2.0)

        for f in fills[prev_fills:]:
            status = "✅" if f.get("success") else "❌"
            print(f"    {status} {f.get('action', '').upper()} {f.get('symbol')} — {f.get('reason')}")

    await asyncio.sleep(3.0)

    print(f"\n{'═' * 60}")
    print(f"  Distributed Replay Complete — {len(fills)} fills")
    for f in fills:
        status = "✅" if f.get("success") else "❌"
        print(f"    {status} {f.get('action', '').upper()} {f.get('symbol')} — {f.get('reason')}")
    print(f"{'═' * 60}\n")

    await bus.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2025-06-01")
    args = parser.parse_args()
    asyncio.run(main(args.start, args.end))
