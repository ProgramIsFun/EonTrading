"""Clear the seen_urls collection so news watcher re-fetches all articles."""
import os
import sys

# Load .env if present
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.data.utils.db_helper import get_mongo_client

db = get_mongo_client()["EonTradingDB"]
count = db.seen_urls.count_documents({})
print(f"seen_urls: {count} documents")
db.seen_urls.drop()
print("seen_urls dropped")
