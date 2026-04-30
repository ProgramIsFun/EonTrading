#!/usr/bin/env python3
"""Clear recent news from MongoDB — useful during development when collection is sparse.

Usage:
  python3 scripts/data/clear_news.py                # clear all
  python3 scripts/data/clear_news.py --days 7       # clear last 7 days
  python3 scripts/data/clear_news.py --origin live   # clear only live-collected
"""
import argparse
from datetime import timedelta
from dotenv import load_dotenv
load_dotenv()

from src.common.clock import utcnow
from src.data.utils.db_helper import get_mongo_client


def main():
    parser = argparse.ArgumentParser(description="Clear news from MongoDB")
    parser.add_argument("--days", type=int, default=0, help="Clear last N days (0 = all)")
    parser.add_argument("--origin", choices=["live", "backfill"], help="Only clear this origin")
    parser.add_argument("--dry-run", action="store_true", help="Show count without deleting")
    args = parser.parse_args()

    col = get_mongo_client()["EonTradingDB"]["news"]
    query = {}

    if args.days > 0:
        cutoff = (utcnow() - timedelta(days=args.days)).isoformat() + "Z"
        query["collected_at"] = {"$gte": cutoff}

    if args.origin:
        query["origin"] = args.origin

    count = col.count_documents(query)
    total = col.count_documents({})

    if args.dry_run:
        print(f"Would delete {count} of {total} documents (query: {query})")
        return

    if count == 0:
        print("Nothing to delete.")
        return

    print(f"Deleting {count} of {total} documents...")
    col.delete_many(query)
    print(f"Done. Remaining: {col.count_documents({})}")


if __name__ == "__main__":
    main()
