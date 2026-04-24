"""Quick price lookup for live trading and replay mode.

Sources:
  - yfinance (default): fetches from Yahoo Finance API
  - clickhouse: reads from local ClickHouse OHLCV data (faster, no API calls)

Set via: PRICE_SOURCE=clickhouse or PRICE_SOURCE=yfinance (default)
"""
import os
from datetime import datetime, timedelta

PRICE_SOURCE = os.getenv("PRICE_SOURCE", "yfinance").lower()


_price_cache: dict[str, float] = {}


def get_price(symbol: str, as_of: str = None) -> float:
    """Get price for a symbol.

    - as_of=None or recent timestamp (< 10min old): fetch latest live price
    - as_of=old timestamp: fetch historical price at that time
    - Caches historical lookups to avoid repeated API calls
    """
    t = _parse_time(as_of)
    is_historical = t and (datetime.utcnow() - t).total_seconds() > 600

    # Cache key for historical lookups
    if is_historical:
        cache_key = f"{symbol}:{t.strftime('%Y-%m-%d-%H')}"
        if cache_key in _price_cache:
            return _price_cache[cache_key]

    if PRICE_SOURCE == "clickhouse":
        price = _from_clickhouse(symbol, as_of if is_historical else None)
    else:
        price = _from_yfinance(symbol, as_of if is_historical else None)

    if is_historical and price > 0:
        _price_cache[cache_key] = price

    return price


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
            print(f"    💲 Fetching {symbol} price @ {t.strftime('%Y-%m-%d %H:%M')}", end="", flush=True)
            data = yf.download(symbol, start=start, end=end, interval="1h", progress=False)
            if not data.empty:
                # Find the closest candle at or before the target time
                data.index = data.index.tz_localize(None) if data.index.tz is None else data.index.tz_convert(None)
                mask = data.index <= t
                if mask.any():
                    data = data[mask]
        else:
            print(f"    💲 Fetching {symbol} latest price", end="", flush=True)
            data = yf.download(symbol, period="1d", interval="1m", progress=False)
        if not data.empty:
            val = data["Close"].iloc[-1]
            price = float(val.iloc[0]) if hasattr(val, "iloc") else float(val)
            print(f" → ${price:.2f}")
            return price
        print(f" → no data")
    except Exception as e:
        print(f" → error: {e}")
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
