"""Reset MongoDB to a clean state. Drops all EonTradingDB collections.

Usage:
  PYTHONPATH=. python scripts/reset_db.py           # interactive confirmation
  PYTHONPATH=. python scripts/reset_db.py --yes     # skip confirmation
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


def main():
    force = "--yes" in sys.argv
    client = get_mongo_client()
    db = client["EonTradingDB"]

    existing = [c for c in COLLECTIONS if c in db.list_collection_names()]
    if not existing:
        print("Nothing to reset — all collections empty.")
        return

    print(f"Will drop {len(existing)} collections from EonTradingDB:")
    for c in existing:
        count = db[c].count_documents({})
        print(f"  {c}: {count} documents")

    if not force:
        answer = input("\nProceed? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    for c in existing:
        db[c].drop()
        print(f"  Dropped {c}")

    print("Done — fresh state.")


if __name__ == "__main__":
    main()
