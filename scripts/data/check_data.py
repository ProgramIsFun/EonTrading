"""Check for invalid OHLCV data: zeros, nulls, negative values, OHLC logic errors."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.storage import ClickHouseStorage

storage = ClickHouseStorage()
checks = [
    ("Zero prices",      "SELECT symbol, count() FROM ohlcv WHERE open=0 OR high=0 OR low=0 OR close=0 GROUP BY symbol ORDER BY count() DESC"),
    ("Zero volume",      "SELECT symbol, count() FROM ohlcv WHERE volume=0 GROUP BY symbol ORDER BY count() DESC"),
    ("Negative values",  "SELECT symbol, count() FROM ohlcv WHERE open<0 OR high<0 OR low<0 OR close<0 OR volume<0 GROUP BY symbol ORDER BY count() DESC"),
    ("High < Low",       "SELECT symbol, count() FROM ohlcv WHERE high < low GROUP BY symbol ORDER BY count() DESC"),
    ("NaN prices",       "SELECT symbol, count() FROM ohlcv WHERE isNaN(open) OR isNaN(high) OR isNaN(low) OR isNaN(close) GROUP BY symbol ORDER BY count() DESC"),
]

total_issues = 0
for name, query in checks:
    rows = storage.client.query(query).result_rows
    count = sum(r[1] for r in rows)
    total_issues += count
    if rows:
        print(f"\n❌ {name}: {count:,} rows across {len(rows)} symbols")
        for sym, cnt in rows[:5]:
            print(f"   {sym}: {cnt:,}")
        if len(rows) > 5:
            print(f"   ... and {len(rows)-5} more symbols")
    else:
        print(f"✅ {name}: clean")

print(f"\n{'='*40}")
total = storage.client.query("SELECT count() FROM ohlcv").result_rows[0][0]
print(f"Total rows: {total:,} | Issues: {total_issues:,}")
