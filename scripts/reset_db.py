"""Reset MongoDB to a clean state. Drops all EonTradingDB collections.

Usage:
  python scripts/reset_db.py           # interactive confirmation
  python scripts/reset_db.py --yes     # skip confirmation
"""
import os
import sys
import pathlib

_root = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_root))
os.chdir(_root)

from dotenv import load_dotenv

load_dotenv(".env")

from src.data.utils.db_helper import get_mongo_client

COLLECTIONS = [
    "orders",
    "positions",
    "news",
    "seen_urls",
    "heartbeats",
    "logs",
    "replay_trades",
]


def reset_db(force=False):
    """Drop all known collections. Returns count of dropped collections."""
    client = get_mongo_client()
    db = client["EonTradingDB"]

    existing = [c for c in COLLECTIONS if c in db.list_collection_names()]
    if not existing:
        print("Nothing to reset — all collections empty.")
        return 0

    print(f"Will drop {len(existing)} collections from EonTradingDB:")
    for c in existing:
        count = db[c].count_documents({})
        print(f"  {c}: {count} documents")

    if not force:
        answer = input("\nProceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return 0

    for c in existing:
        db[c].drop()
        print(f"  Dropped {c}")

    print("Done — fresh state.")
    return len(existing)


def main():
    force = "--yes" in sys.argv
    reset_db(force=force)


if __name__ == "__main__":
    main()
