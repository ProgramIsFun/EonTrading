#!/usr/bin/env python3
"""Drop all MongoDB collections except ``news`` — quick development reset.

Usage::

    python scripts/data/reset_collections.py              # drop all except news
    python scripts/data/reset_collections.py --dry-run    # show what would be dropped
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv

load_dotenv()

from src.data.utils.db_helper import get_mongo_client


def main():
    parser = argparse.ArgumentParser(description="Drop all collections except news")
    parser.add_argument("--dry-run", action="store_true", help="List collections without dropping")
    args = parser.parse_args()

    db = get_mongo_client()["EonTradingDB"]
    keep = {"news"}

    all_cols = db.list_collection_names()
    to_drop = [c for c in all_cols if c not in keep]

    if not to_drop:
        print("No collections to drop (only 'news' exists).")
        return

    print(f"Keeping: {', '.join(sorted(keep))}")
    print(f"Dropping ({len(to_drop)}): {', '.join(sorted(to_drop))}")

    if args.dry_run:
        print("\nDry run — nothing deleted.")
        return

    confirm = input("\nConfirm drop? [y/N] ")
    if confirm.lower() != "y":
        print("Cancelled.")
        return

    for col_name in to_drop:
        db[col_name].drop()
        print(f"  Dropped '{col_name}'")

    print("\nDone. Only 'news' remains.")


if __name__ == "__main__":
    main()
