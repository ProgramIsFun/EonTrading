"""Quick price lookup for live trading and replay mode.

Sources:
  - yfinance (default): fetches from Yahoo Finance API
  - clickhouse: reads from local ClickHouse OHLCV data (faster, no API calls)

Set via: PRICE_SOURCE=clickhouse or PRICE_SOURCE=yfinance (default)
"""
import os
from datetime import timedelta
from src.common.clock import clock

PRICE_SOURCE = os.getenv("PRICE_SOURCE", "yfinance").lower()


def get_price(symbol: str) -> float:
    """Get price for a symbol. Uses clock — live gets latest, replay gets historical."""
    if PRICE_SOURCE == "clickhouse":
        return _from_clickhouse(symbol)
    return _from_yfinance(symbol)


def _from_yfinance(symbol: str) -> float:
    import yfinance as yf
    try:
        if clock.is_replay:
            t = clock.now()
            start = (t - timedelta(days=5)).strftime("%Y-%m-%d")
            end = (t + timedelta(days=1)).strftime("%Y-%m-%d")
            data = yf.download(symbol, start=start, end=end, progress=False)
        else:
            data = yf.download(symbol, period="1d", interval="1m", progress=False)
        if not data.empty:
            val = data["Close"].iloc[-1]
            return float(val.iloc[0]) if hasattr(val, "iloc") else float(val)
    except Exception as e:
        print(f"  ⚠️ yfinance price lookup failed for {symbol}: {e}")
    return 0.0


def _from_clickhouse(symbol: str) -> float:
    try:
        from src.data.storage.clickhouse_storage import ClickHouseStorage
        storage = ClickHouseStorage()
        t = clock.now()
        start = (t - timedelta(days=5)).strftime("%Y-%m-%d")
        end = (t + timedelta(days=1)).strftime("%Y-%m-%d")
        df = storage.query_ohlcv(symbol, "1d", start, end)
        if not df.empty:
            return float(df["close"].iloc[-1])
    except Exception as e:
        print(f"  ⚠️ ClickHouse price lookup failed for {symbol}: {e}")
    return 0.0
