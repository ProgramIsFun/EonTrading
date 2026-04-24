"""Quick price lookup for live trading and replay mode.

Sources:
  - yfinance (default): fetches from Yahoo Finance API
  - clickhouse: reads from local ClickHouse OHLCV data (faster, no API calls)

Set via: PRICE_SOURCE=clickhouse or PRICE_SOURCE=yfinance (default)
"""
import os
from datetime import datetime, timedelta

PRICE_SOURCE = os.getenv("PRICE_SOURCE", "yfinance").lower()


def get_price(symbol: str, as_of: str = None) -> float:
    """Get price for a symbol. If as_of is provided (ISO string), fetch historical price."""
    if PRICE_SOURCE == "clickhouse":
        return _from_clickhouse(symbol, as_of)
    return _from_yfinance(symbol, as_of)


def _parse_time(as_of: str = None) -> datetime | None:
    if not as_of:
        return None
    try:
        return datetime.fromisoformat(as_of.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _from_yfinance(symbol: str, as_of: str = None) -> float:
    import yfinance as yf
    try:
        t = _parse_time(as_of)
        if t:
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


def _from_clickhouse(symbol: str, as_of: str = None) -> float:
    try:
        from src.data.storage.clickhouse_storage import ClickHouseStorage
        t = _parse_time(as_of) or datetime.utcnow()
        storage = ClickHouseStorage()
        start = (t - timedelta(days=5)).strftime("%Y-%m-%d")
        end = (t + timedelta(days=1)).strftime("%Y-%m-%d")
        df = storage.query_ohlcv(symbol, "1d", start, end)
        if not df.empty:
            return float(df["close"].iloc[-1])
    except Exception as e:
        print(f"  ⚠️ ClickHouse price lookup failed for {symbol}: {e}")
    return 0.0
