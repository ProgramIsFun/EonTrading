"""Tests for reconcile — position comparison between system and broker."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.common.reconcile import reconcile


@pytest.fixture
def broker():
    b = AsyncMock()
    b.get_positions.return_value = {}
    b.get_cash.return_value = 10000.0
    return b


@pytest.fixture
def store():
    s = MagicMock()
    s.get_positions_with_prices.return_value = {}
    return s


class TestReconcile:
    pytestmark = pytest.mark.asyncio

    async def test_empty_positions_no_issues(self, broker, store):
        result = await reconcile(broker, store)
        assert result["ok"] is True
        assert result["issues"] == []
        assert result["broker_cash"] == 10000.0

    async def test_matched_positions_no_issues(self, broker, store):
        store.get_positions_with_prices.return_value = {
            "AAPL": {"entryTime": "...", "entryPrice": 150, "qty": 10},
        }
        broker.get_positions.return_value = {"AAPL": 10}

        result = await reconcile(broker, store)
        assert result["ok"] is True
        assert result["matched"] == ["AAPL"]

    async def test_missing_in_broker(self, broker, store):
        store.get_positions_with_prices.return_value = {
            "AAPL": {"entryTime": "...", "entryPrice": 150, "qty": 10},
        }
        broker.get_positions.return_value = {}

        result = await reconcile(broker, store)
        assert result["ok"] is False
        assert any(i["symbol"] == "AAPL" and "not in broker" in i["issue"] for i in result["issues"])

    async def test_missing_in_system(self, broker, store):
        store.get_positions_with_prices.return_value = {}
        broker.get_positions.return_value = {"AAPL": 10}

        result = await reconcile(broker, store)
        assert result["ok"] is False
        assert any(i["symbol"] == "AAPL" and "not in system" in i["issue"] for i in result["issues"])

    async def test_qty_mismatch(self, broker, store):
        store.get_positions_with_prices.return_value = {
            "AAPL": {"entryTime": "...", "entryPrice": 150, "qty": 10},
        }
        broker.get_positions.return_value = {"AAPL": 5}

        result = await reconcile(broker, store)
        assert result["ok"] is False
        assert any(i["symbol"] == "AAPL" and "qty mismatch" in i["issue"] for i in result["issues"])

    async def test_multiple_issues(self, broker, store):
        store.get_positions_with_prices.return_value = {
            "AAPL": {"entryTime": "...", "entryPrice": 150, "qty": 10},
            "GOOGL": {"entryTime": "...", "entryPrice": 200, "qty": 5},
        }
        broker.get_positions.return_value = {"AAPL": 10, "TSLA": 20}

        result = await reconcile(broker, store)
        assert result["ok"] is False
        issues_by_sym = {i["symbol"]: i["issue"] for i in result["issues"]}
        assert "GOOGL" in issues_by_sym and "not in broker" in issues_by_sym["GOOGL"]
        assert "TSLA" in issues_by_sym and "not in system" in issues_by_sym["TSLA"]
        assert "AAPL" not in issues_by_sym  # matched correctly
