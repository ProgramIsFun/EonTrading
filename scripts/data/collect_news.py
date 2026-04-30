#!/usr/bin/env python3
"""Collect news from free sources (RSS + Reddit) and store to MongoDB.

Run continuously or via cron:
  python3 -m scripts.collect_news          # run once
  python3 -m scripts.collect_news --loop   # poll every 5 min
"""
import time, argparse
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from src.common.clock import utcnow

load_dotenv()

from src.common.news_poller import NewsPoller
from src.data.news import RSSSource, RedditSource
from src.data.utils.db_helper import get_mongo_client

DB_NAME = "EonTradingDB"
COLLECTION = "news"
POLL_INTERVAL = 300


def get_collection():
    client = get_mongo_client()
    col = client[DB_NAME][COLLECTION]
    col.create_index("url", unique=True, sparse=True)
    return col


def collect_once(poller, col):
    total = 0
    for ev in poller.poll_once():
        try:
            col.insert_one({
                "source": ev.source, "headline": ev.headline,
                "timestamp": ev.timestamp, "url": ev.url, "body": ev.body,
                "collected_at": utcnow().isoformat() + "Z",
            })
            total += 1
            print(f"  + [{ev.source}] {ev.headline[:70]}")
        except Exception:
            pass  # duplicate URL — already in collection
    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--loop", action="store_true", help="Poll continuously")
    args = parser.parse_args()

    poller = NewsPoller(
        sources=[RSSSource(), RedditSource()],
        interval_sec=POLL_INTERVAL,
        persist_seen=True,
    )
    col = get_collection()

    print(f"News collector started — sources: RSS, Reddit")
    print(f"Storing to MongoDB: {DB_NAME}.{COLLECTION}")

    if args.loop:
        while True:
            print(f"\n[{utcnow().strftime('%H:%M:%S')}] Polling...")
            n = collect_once(poller, col)
            print(f"  Collected {n} new articles (total in DB: {col.count_documents({})})")
            time.sleep(poller.interval)
    else:
        n = collect_once(poller, col)
        print(f"\nCollected {n} new articles (total in DB: {col.count_documents({})})")


if __name__ == "__main__":
    main()
