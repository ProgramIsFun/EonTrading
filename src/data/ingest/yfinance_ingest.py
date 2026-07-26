"""Ingest OHLCV data from providers into storage."""
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf
from tqdm import tqdm

from ..storage.base_storage import StorageBackend


def normalize_yfinance_df(df: pd.DataFrame, date_column: str = "timestamp") -> pd.DataFrame:
    """Lowercase columns and rename the date column to *date_column*.

    Handles yfinance's MultiIndex columns (single-ticker produces tuples).
    """
    df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
    for alias in ("datetime", "date"):
        if alias in df.columns:
            df = df.rename(columns={alias: date_column})
            break
    if date_column in df.columns:
        df[date_column] = pd.to_datetime(df[date_column], utc=True)
    return df


def ingest_yfinance(
    symbols: list[str],
    storage: StorageBackend,
    exchange: str,
    interval: str = "1d",
    period: str | None = None,
    start: str | None = None,
    end: str | None = None,
    batch_size: int = 50,
):
    """
    Ingest OHLCV from yfinance into storage.
    If no period/start/end given, resumes from last stored timestamp.
    """
    for i in tqdm(range(0, len(symbols), batch_size), desc="Ingesting"):
        batch = symbols[i:i + batch_size]

        kwargs = {"group_by": "ticker", "interval": interval, "threads": False, "progress": False}
        if period:
            kwargs["period"] = period
        elif start:
            kwargs["start"] = start
            if end:
                kwargs["end"] = end
        else:
            # resume mode: use latest timestamp + 1 day as start
            kwargs["period"] = "5d"

        data = yf.download(batch, **kwargs)
        if data.empty:
            continue

        for symbol in batch:
            try:
                if len(batch) == 1:
                    df = data
                else:
                    df = data[symbol] if symbol in data.columns.get_level_values(0) else pd.DataFrame()

                if df.empty or df.dropna(how="all").empty:
                    continue

                df = df.dropna(subset=["Close"])
                df = df.reset_index()
                ts_col = "Datetime" if "Datetime" in df.columns else "Date"
                df = df.rename(columns={
                    ts_col: "timestamp",
                    "Open": "open", "High": "high", "Low": "low",
                    "Close": "close", "Volume": "volume",
                })
                df = df[["timestamp", "open", "high", "low", "close", "volume"]]
                df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

                storage.insert_ohlcv(df, symbol=symbol, exchange=exchange, interval=interval)
            except Exception as e:
                print(f"  Error {symbol}: {e}")
