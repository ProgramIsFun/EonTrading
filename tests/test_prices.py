"""Tests for shared price fetching (src/backtest/prices.py)."""
import pandas as pd

from src.backtest.prices import fetch_price_data


def _fake_download(symbol, start=None, end=None, interval=None, **kwargs):
    n = 24 if interval == "1h" else 5
    idx = pd.date_range("2025-01-01", periods=n, freq="h" if interval == "1h" else "D")
    idx.name = "Date"
    return pd.DataFrame({
        "Open": [100.0] * n,
        "High": [105.0] * n,
        "Low": [95.0] * n,
        "Close": [102.0] * n,
        "Volume": [1000] * n,
    }, index=idx)


def test_returns_normalized_frame(monkeypatch):
    monkeypatch.setattr("src.backtest.prices.yf.download", _fake_download)
    df = fetch_price_data("NORM", "2025-01-01", "2025-01-05")
    assert "timestamp" in df.columns
    assert {"open", "high", "low", "close", "volume"}.issubset(df.columns)
    assert len(df) == 24
    assert df._interval == "1h"


def test_daily_fallback_when_interval_missing(monkeypatch):
    calls = {}

    def flaky(symbol, start=None, end=None, interval=None, **kwargs):
        calls["interval"] = interval
        if interval == "1h":
            raise ValueError("interval not supported")
        return _fake_download(symbol, start=start, end=end, interval=interval)

    monkeypatch.setattr("src.backtest.prices.yf.download", flaky)
    df = fetch_price_data("FALLBACK", "2025-01-01", "2025-01-05")
    assert calls["interval"] == "1d"
    assert df._interval == "1d"


def test_caches_results(monkeypatch):
    hits = {"n": 0}

    def counting(symbol, start=None, end=None, interval=None, **kwargs):
        hits["n"] += 1
        return _fake_download(symbol, start=start, end=end, interval=interval)

    monkeypatch.setattr("src.backtest.prices.yf.download", counting)
    fetch_price_data("CACHED", "2025-01-01", "2025-01-05")
    fetch_price_data("CACHED", "2025-01-01", "2025-01-05")
    assert hits["n"] == 1


def test_empty_dataframe_when_download_fails(monkeypatch):
    def failing(symbol, start=None, end=None, interval=None, **kwargs):
        return None

    monkeypatch.setattr("src.backtest.prices.yf.download", failing)
    df = fetch_price_data("FAILSYM", "2025-01-01", "2025-01-05")
    assert df.empty
