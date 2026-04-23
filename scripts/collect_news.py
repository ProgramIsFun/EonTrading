#!/usr/bin/env python3
"""Collect news from free sources (RSS + Reddit) and store to MongoDB.

Run continuously or via cron:
  python3 -m scripts.collect_news          # run once
  python3 -m scripts.collect_news --loop   # poll every 5 min
"""
import os, sys, time, argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.data.news import RSSSource, RedditSource
from src.data.utils.db_helper import get_mongo_client

DB_NAME = "EonTradingDB"
COLLECTION = "news"
POLL_INTERVAL = 300  # 5 minutes


def get_collection():
    client = get_mongo_client()
    return client[DB_NAME][COLLECTION]


def collect_once(sources, col):
    total = 0
    for source in sources:
        events = source.fetch_latest()
        for ev in events:
            # Dedup by URL
            if ev.url and col.find_one({"url": ev.url}):
                continue
            doc = {
                "source": ev.source,
                "headline": ev.headline,
                "timestamp": ev.timestamp,
                "url": ev.url,
                "body": ev.body,
                "collected_at": datetime.utcnow().isoformat() + "Z",
            }
            col.insert_one(doc)
            total += 1
            print(f"  + [{ev.source}] {ev.headline[:70]}")
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Poll continuously")
    args = parser.parse_args()

    sources = [
        RSSSource(),
        RedditSource(),
    ]

    col = get_collection()
    # Create index for dedup
    col.create_index("url", unique=True, sparse=True)

    print(f"News collector started — sources: RSS, Reddit")
    print(f"Storing to MongoDB: {DB_NAME}.{COLLECTION}")

    if args.loop:
        while True:
            print(f"\n[{datetime.utcnow().strftime('%H:%M:%S')}] Polling...")
            n = collect_once(sources, col)
            print(f"  Collected {n} new articles (total in DB: {col.count_documents({})})")
            time.sleep(POLL_INTERVAL)
    else:
        n = collect_once(sources, col)
        print(f"\nCollected {n} new articles (total in DB: {col.count_documents({})})")


if __name__ == "__main__":
    main()
