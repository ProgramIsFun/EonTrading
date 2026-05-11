"""Daily update: fetch latest S&P 500 data since last stored timestamp."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SSL_CERT_FILE", os.popen("python3 -c 'import certifi; print(certifi.where())'").read().strip())

from datetime import timedelta

from src.data.ingest import ingest_yfinance
from src.data.storage import ClickHouseStorage

storage = ClickHouseStorage()

with open("config/sp500.txt") as f:
    symbols = [s.strip() for s in f if s.strip()]

# Find the latest date we have
latest = storage.get_latest_timestamp(symbols[0], "1d")
if latest is None:
    print("No data found. Run backfill_sp500.py first.")
    sys.exit(1)

start = (latest + timedelta(days=1)).strftime("%Y-%m-%d")
print(f"Updating {len(symbols)} symbols from {start}...")
ingest_yfinance(symbols, storage, exchange="US", interval="1d", start=start)

result = storage.client.query("SELECT count(), max(timestamp) FROM ohlcv WHERE exchange = 'US'")
rows, max_ts = result.result_rows[0]
print(f"Done. {rows:,} total rows, latest: {max_ts}")
