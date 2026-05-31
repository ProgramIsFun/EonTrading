"""Tests for price module — cache, source fallback, time parsing."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.common.price import _cache_get, _cache_set, _parse_time, get_price


class TestParseTime:
    def test_none_returns_none(self):
        assert _parse_time(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_time("") is None

    def test_iso_with_z(self):
        t = _parse_time("2026-05-31T10:30:00Z")
        assert t == datetime(2026, 5, 31, 10, 30, 0)

    def test_iso_without_z(self):
        t = _parse_time("2026-05-31T10:30:00")
        assert t == datetime(2026, 5, 31, 10, 30, 0)

    def test_invalid_returns_none(self):
        assert _parse_time("not-a-date") is None


class TestCache:
    def test_cache_set_and_get(self):
        _cache_set("TEST:2026-05-31-10", 150.5)
        assert _cache_get("TEST:2026-05-31-10") == 150.5

    def test_cache_miss_returns_none(self):
        assert _cache_get("NONEXISTENT:9999-01-01-00") is None


class TestGetPrice:
    @patch("src.common.price._from_yfinance", return_value=150.0)
    @patch("src.common.price.PRICE_SOURCE", "yfinance")
    def test_live_price_calls_yfinance(self, mock_yf):
        price = get_price("AAPL")
        assert price == 150.0

    @patch("src.common.price._from_clickhouse", return_value=200.0)
    @patch("src.common.price.PRICE_SOURCE", "clickhouse")
    def test_live_price_calls_clickhouse(self, mock_ch):
        price = get_price("AAPL")
        assert price == 200.0

    @patch("src.common.price._from_yfinance", return_value=0.0)
    @patch("src.common.price.PRICE_SOURCE", "yfinance")
    def test_failed_fetch_returns_zero(self, mock_yf):
        price = get_price("AAPL")
        assert price == 0.0

    @patch("src.common.price._from_yfinance", return_value=300.0)
    @patch("src.common.price.PRICE_SOURCE", "yfinance")
    def test_historical_price_cached(self, mock_yf):
        # First call — fetches and caches
        t = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        p1 = get_price("AAPL", as_of=t)
        assert p1 == 300.0
        assert mock_yf.call_count == 1

        # Second call with same hour — should use cache, not fetch again
        p2 = get_price("AAPL", as_of=t)
        assert p2 == 300.0
        assert mock_yf.call_count == 1  # not incremented

    @patch("src.common.price._parse_time", return_value=datetime(2026, 5, 31, 10, 0, 0))
    def test_history_uses_cache_before_source(self, mock_parse):
        cache_key = "AAPL:2026-05-31-10"
        _cache_set(cache_key, 999.0)
        with patch("src.common.price.utcnow") as mock_now:
            mock_now.return_value = datetime(2026, 6, 1, 10, 0, 0)  # > 10min old
            with patch("src.common.price._from_yfinance") as mock_yf:
                price = get_price("AAPL", as_of="2026-05-31T10:00:00Z")
                assert price == 999.0
                mock_yf.assert_not_called()
