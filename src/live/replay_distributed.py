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

SAMPLE_NEWS = [
    {"date": "2025-01-06T10:00:00", "headline": "Nvidia unveils new Blackwell GPU chips at CES, stock rallies"},
    {"date": "2025-01-27T09:30:00", "headline": "DeepSeek AI model shocks market, Nvidia stock crashes on cheaper AI fears"},
    {"date": "2025-01-29T16:30:00", "headline": "Meta Q4 earnings beat estimates, ad revenue growth accelerates"},
    {"date": "2025-01-30T16:30:00", "headline": "Apple reports record Q1 revenue of $124B, beating estimates"},
    {"date": "2025-02-06T16:30:00", "headline": "Amazon Q4 earnings beat estimates, AWS revenue growth accelerates"},
    {"date": "2025-02-14T10:00:00", "headline": "Meta announces massive AI spending increase to $65B, stock drops on cost fears"},
    {"date": "2025-02-26T16:30:00", "headline": "Nvidia Q4 earnings smash records, data center revenue surges 93%"},
    {"date": "2025-03-12T10:00:00", "headline": "Google acquires cloud security firm Wiz for $32B, biggest deal ever"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump announces sweeping tariffs on China, Apple supply chain at risk"},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs for 90 days, Apple stock surges on relief rally"},
    {"date": "2025-04-23T10:00:00", "headline": "Elon Musk says he will reduce DOGE role to focus on Tesla, stock surges"},
    {"date": "2025-04-24T16:30:00", "headline": "Alphabet Q1 earnings beat estimates, cloud revenue surges, stock rallies"},
    {"date": "2025-04-30T16:30:00", "headline": "Meta Q1 earnings crush expectations, revenue up 16% on strong ad demand"},
    {"date": "2025-04-30T16:30:00", "headline": "Microsoft Q3 earnings crush estimates, Azure growth reaccelerates to 35%"},
    {"date": "2025-05-01T16:30:00", "headline": "Apple Q2 earnings beat expectations, services revenue hits record"},
]


async def main(start: str, end: str):
    from src.common.event_bus import RedisEventBus
    from src.common.events import CHANNEL_NEWS, NewsEvent

    redis_host = os.getenv("REDIS_HOST", "localhost")
    bus = RedisEventBus(host=redis_host)
    await bus.subscribe("fill", lambda _: None)
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
