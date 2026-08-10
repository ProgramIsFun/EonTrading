"""Shared yfinance price fetching for backtests (interval with daily fallback, cached)."""
import logging

import pandas as pd
import yfinance as yf

from ..data.ingest.yfinance_ingest import normalize_yfinance_df

logger = logging.getLogger(__name__)

_price_cache: dict[str, pd.DataFrame] = {}


def fetch_price_data(symbol: str, start: str, end: str, interval: str = "1h",
                     date_column: str = "timestamp") -> pd.DataFrame:
    """Fetch OHLCV for a symbol, falling back from *interval* to daily data.

    Normalizes columns (via normalize_yfinance_df), names the date column
    *date_column*, and tags the result with ``_interval`` so callers know which
    bar size was actually returned. Results are cached per
    (symbol, start, end, interval, date_column).
    """
    cache_key = f"{symbol}:{start}:{end}:{interval}:{date_column}"
    cached = _price_cache.get(cache_key)
    if cached is not None:
        return cached

    used_interval = interval
    df = _download(symbol, start, end, interval)
    if df is None and interval != "1d":
        logger.debug("Interval %s unavailable for %s, falling back to 1d", interval, symbol)
        used_interval = "1d"
        df = _download(symbol, start, end, "1d")
    if df is None:
        df = pd.DataFrame()
    if not df.empty:
        df = df.reset_index()
        df = normalize_yfinance_df(df, date_column=date_column)
    df._interval = used_interval
    _price_cache[cache_key] = df
    return df


def _download(symbol: str, start: str, end: str, interval: str) -> pd.DataFrame | None:
    try:
        df = yf.download(symbol, start=start, end=end, interval=interval,
                         auto_adjust=True, progress=False, timeout=15)
        return df if df is not None and not df.empty else None
    except Exception:
        return None
