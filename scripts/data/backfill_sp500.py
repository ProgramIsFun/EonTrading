"""Backfill S&P 500 daily data from yfinance into ClickHouse."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("SSL_CERT_FILE", os.popen("python3 -c 'import certifi; print(certifi.where())'").read().strip())

from src.data.ingest import ingest_yfinance
from src.data.storage import ClickHouseStorage

storage = ClickHouseStorage()

with open("config/sp500.txt") as f:
    symbols = [s.strip() for s in f if s.strip()]

print(f"Backfilling {len(symbols)} S&P 500 symbols, daily, max history...")
ingest_yfinance(symbols, storage, exchange="US", interval="1d", period="max", batch_size=50)

# Verify
result = storage.client.query("SELECT count(), uniq(symbol) FROM ohlcv WHERE exchange = 'US'")
rows, syms = result.result_rows[0]
print(f"\nDone. {rows:,} total rows, {syms} unique symbols in ClickHouse.")
