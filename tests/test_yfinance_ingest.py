"""Tests for yfinance_ingest — normalize_yfinance_df."""
import pandas as pd
import pytest

from src.data.ingest.yfinance_ingest import normalize_yfinance_df


class TestNormalizeYfinanceDf:
    def test_renames_date_column(self):
        df = pd.DataFrame({"Date": ["2025-01-01"], "Open": [100]})
        result = normalize_yfinance_df(df)
        assert "timestamp" in result.columns
        assert "date" not in result.columns

    def test_renames_datetime_column(self):
        df = pd.DataFrame({"Datetime": ["2025-01-01"], "Open": [100]})
        result = normalize_yfinance_df(df)
        assert "timestamp" in result.columns
        assert "datetime" not in result.columns

    def test_custom_date_column_name(self):
        df = pd.DataFrame({"Date": ["2025-01-01"], "Open": [100]})
        result = normalize_yfinance_df(df, date_column="date")
        assert "date" in result.columns
        assert "timestamp" not in result.columns

    def test_lowercase_columns(self):
        df = pd.DataFrame({"Date": ["2025-01-01"], "Open": [100], "High": [110]})
        result = normalize_yfinance_df(df)
        assert "open" in result.columns
        assert "high" in result.columns
        assert "Open" not in result.columns

    def test_multiticker_tuples(self):
        df = pd.DataFrame({("Date", ""): ["2025-01-01"], ("Open", "AAPL"): [100]})
        result = normalize_yfinance_df(df)
        assert "open" in result.columns or ("open", "aapl") in result.columns

    def test_converts_timestamp_to_datetime(self):
        df = pd.DataFrame({"Date": ["2025-01-01T00:00:00Z"], "Open": [100]})
        result = normalize_yfinance_df(df)
        assert pd.api.types.is_datetime64_any_dtype(result["timestamp"])

    def test_preserves_existing_timestamp(self):
        df = pd.DataFrame({"timestamp": ["2025-01-01"], "Open": [100]})
        result = normalize_yfinance_df(df)
        assert "timestamp" in result.columns

    def test_no_date_column_passthrough(self):
        df = pd.DataFrame({"Open": [100], "Close": [105]})
        result = normalize_yfinance_df(df)
        assert "open" in result.columns
        assert "close" in result.columns
