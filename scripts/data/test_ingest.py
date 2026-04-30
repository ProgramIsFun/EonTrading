"""Quick test: ingest a few symbols and query them back."""
from src.data.storage import ClickHouseStorage
from src.data.ingest import ingest_yfinance

storage = ClickHouseStorage()

# Ingest 5 days of daily data for a few test symbols
symbols = ["0700.HK", "AAPL", "MSFT"]
print("Ingesting test data...")
ingest_yfinance(symbols, storage, exchange="TEST", interval="1d", period="5d")

# Query it back
from datetime import datetime, timedelta
from src.common.clock import utcnow
end = utcnow()
start = end - timedelta(days=10)

for sym in symbols:
    df = storage.query_ohlcv(sym, "1d", start, end)
    print(f"\n{sym}: {len(df)} rows")
    if not df.empty:
        print(df.to_string(index=False))
