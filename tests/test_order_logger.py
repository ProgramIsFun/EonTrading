"""Tests for order_logger — verifies error handling and log levels."""
from unittest.mock import MagicMock, patch

import pytest

from src.common.events import TradeEvent
from src.live.order_logger import mongo_log_order


def _make_trade(**kwargs):
    defaults = {
        "symbol": "AAPL",
        "action": "buy",
        "price": 150.0,
        "size": 10,
        "reason": "sentiment",
        "timestamp": "2025-01-01T00:00:00",
    }
    defaults.update(kwargs)
    return TradeEvent(**defaults)


class TestMongoLogOrder:
    @pytest.mark.asyncio
    async def test_logs_warning_on_mongodb_failure(self):
        trade = _make_trade()
        failing_store = MagicMock()
        failing_store.insert.side_effect = ConnectionError("mongo down")

        with patch("src.live.order_logger.logger.warning") as mock_warn:
            await mongo_log_order(trade, "order-123", "paper", order_store=failing_store)

        mock_warn.assert_called_once()
        args = mock_warn.call_args[0]
        assert "order-123" in args[1]
        assert "Failed to log order" in args[0]

    @pytest.mark.asyncio
    async def test_logs_warning_with_exc_info(self):
        trade = _make_trade()
        failing_store = MagicMock()
        failing_store.insert.side_effect = RuntimeError("unexpected")

        with patch("src.live.order_logger.logger.warning") as mock_warn:
            await mongo_log_order(trade, "order-456", "alpaca", order_store=failing_store)

        assert mock_warn.call_args[1].get("exc_info") is True

    @pytest.mark.asyncio
    async def test_success_does_not_log_warning(self):
        trade = _make_trade()
        ok_store = MagicMock()

        with patch("src.live.order_logger.logger.warning") as mock_warn:
            await mongo_log_order(trade, "order-789", "paper", order_store=ok_store)

        mock_warn.assert_not_called()
        ok_store.insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_order_inserts_with_status_failed(self):
        trade = _make_trade()
        store = MagicMock()

        await mongo_log_order(trade, None, "paper", order_store=store, status="failed", error="broker returned None")

        doc = store.insert.call_args[0][0]
        assert doc["status"] == "failed"
        assert doc["order_id"] is None
        assert doc["error"] == "broker returned None"
        assert doc["symbol"] == "AAPL"
        assert doc["placed_at"] is None
        assert doc["next_check_at"] is None

    @pytest.mark.asyncio
    async def test_pending_order_has_placed_at(self):
        trade = _make_trade()
        store = MagicMock()

        await mongo_log_order(trade, "order-123", "paper", order_store=store)

        doc = store.insert.call_args[0][0]
        assert doc["status"] == "pending"
        assert doc["placed_at"] is not None
        assert doc["next_check_at"] is not None

    @pytest.mark.asyncio
    async def test_failed_order_logs_warning_on_mongodb_failure(self):
        trade = _make_trade()
        failing_store = MagicMock()
        failing_store.insert.side_effect = ConnectionError("mongo down")

        with patch("src.live.order_logger.logger.warning") as mock_warn:
            await mongo_log_order(trade, None, "paper", order_store=failing_store, status="failed", error="broker returned None")

        mock_warn.assert_called_once()
        assert "Failed to log order" in mock_warn.call_args[0][0]
