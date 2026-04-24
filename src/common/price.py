"""Quick price lookup for live trading and replay mode.

Sources:
  - yfinance (default): fetches from Yahoo Finance API
  - clickhouse: reads from local ClickHouse OHLCV data (faster, no API calls)

Set via: PRICE_SOURCE=clickhouse or PRICE_SOURCE=yfinance (default)
"""
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
PRICE_SOURCE = os.getenv("PRICE_SOURCE", "yfinance").lower()
_YFINANCE_TIMEOUT = int(os.getenv("PRICE_TIMEOUT", "15"))


_price_cache: dict[str, float] = {}
_redis_cache = None


def _get_redis():
    global _redis_cache
    if _redis_cache is not None:
        return _redis_cache
    try:
        import redis
        import os
        host = os.getenv("REDIS_HOST")
        if host:
            _redis_cache = redis.Redis(host=host, port=6379, decode_responses=True)
            _redis_cache.ping()
            return _redis_cache
    except Exception:
        pass
    _redis_cache = False  # mark as unavailable
    return False


def _cache_get(key: str) -> float | None:
    r = _get_redis()
    if r:
        val = r.get(f"replay:price:{key}")
        if val:
            return float(val)
    return _price_cache.get(key)


def _cache_set(key: str, price: float):
    _price_cache[key] = price
    r = _get_redis()
    if r:
        r.setex(f"replay:price:{key}", 300, str(price))  # expire after 5 min


def get_price(symbol: str, as_of: str = None) -> float:
    """Get price for a symbol.

    - as_of=None or recent timestamp (< 10min old): fetch latest live price
    - as_of=old timestamp: fetch historical price at that time
    - Caches via Redis (if available) or in-memory dict
    """
    t = _parse_time(as_of)
    is_historical = t and (datetime.utcnow() - t).total_seconds() > 600

    if is_historical:
        cache_key = f"{symbol}:{t.strftime('%Y-%m-%d-%H')}"
        cached = _cache_get(cache_key)
        if cached:
            return cached

    if PRICE_SOURCE == "clickhouse":
        price = _from_clickhouse(symbol, as_of if is_historical else None)
    else:
        price = _from_yfinance(symbol, as_of if is_historical else None)

    if is_historical and price > 0:
        _cache_set(cache_key, price)

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
            logger.info("Fetching %s price @ %s", symbol, t.strftime('%Y-%m-%d %H:%M'))
            data = yf.download(symbol, start=start, end=end, interval="1h", progress=False, timeout=_YFINANCE_TIMEOUT)
            if not data.empty:
                # Find the closest candle at or before the target time
                data.index = data.index.tz_localize(None) if data.index.tz is None else data.index.tz_convert(None)
                mask = data.index <= t
                if mask.any():
                    data = data[mask]
        else:
            logger.info("Fetching %s latest price", symbol)
            data = yf.download(symbol, period="1d", interval="1m", progress=False, timeout=_YFINANCE_TIMEOUT)
        if not data.empty:
            val = data["Close"].iloc[-1]
            price = float(val.iloc[0]) if hasattr(val, "iloc") else float(val)
            logger.info("%s → $%.2f", symbol, price)
            return price
        logger.warning("%s → no data", symbol)
    except Exception as e:
        logger.error("%s → error: %s", symbol, e)
    return 0.0


def _from_clickhouse(symbol: str, as_of: str = None) -> float:
    try:
        from src.data.storage.clickhouse_storage import ClickHouseStorage
        t = _parse_time(as_of) or datetime.utcnow()
        storage = ClickHouseStorage()
        start = (t - timedelta(days=5)).strftime("%Y-%m-%d")
        end = (t + timedelta(days=1)).strftime("%Y-%m-%d")
        # Try hourly first, fall back to daily
        for interval in ["1h", "1d"]:
            logger.info("[ClickHouse] %s @ %s (%s)", symbol, t.strftime('%Y-%m-%d %H:%M'), interval)
            df = storage.query_ohlcv(symbol, interval, start, end)
            if not df.empty:
                # For hourly, find closest candle at or before target time
                if interval == "1h" and "timestamp" in df.columns:
                    df["timestamp"] = df["timestamp"].dt.tz_localize(None) if df["timestamp"].dt.tz is not None else df["timestamp"]
                    mask = df["timestamp"] <= t
                    if mask.any():
                        df = df[mask]
                price = float(df["close"].iloc[-1])
                logger.info("%s → $%.2f", symbol, price)
                return price
            logger.warning("%s (%s) → no data", symbol, interval)
    except Exception as e:
        logger.error("%s → error: %s", symbol, e)
    return 0.0
