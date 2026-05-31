"""Tests for OrderTracker — mocked MongoDB, no real connection needed."""
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.common.clock import utcnow
from src.common.events import TradeEvent


def _make_doc(overrides=None):
    now = utcnow()
    doc = {
        "_id": "abc123",
        "order_id": "ord-001",
        "broker_type": "FutuBroker",
        "symbol": "AAPL",
        "action": "buy",
        "price": 150.0,
        "shares": 10,
        "status": "pending",
        "placed_at": now,
        "checked_at": None,
        "filled_at": None,
        "cancelled_at": None,
        "next_check_at": now,
        "retry_count": 0,
        "error": None,
    }
    if overrides:
        doc.update(overrides)
    return doc


@pytest.fixture
def mock_mongo():
    mock_pending = MagicMock()
    mock_trades = MagicMock()
    mock_positions = MagicMock()

    with patch("src.common.order_tracker.get_mongo_client") as m:
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(side_effect=lambda name: {
            "pending_orders": mock_pending,
            "trades": mock_trades,
            "positions": mock_positions,
        }[name])
        m.return_value.__getitem__ = MagicMock(return_value=mock_db)

        tracker = _build_tracker()
        tracker._col = mock_pending

        yield tracker, mock_pending, mock_trades, mock_positions


def _build_tracker(**kwargs):
    from src.common.order_tracker import OrderTracker

    bus = MagicMock()
    broker = MagicMock()
    return OrderTracker(bus, broker, **kwargs)


# ---------------------------------------------------------------------------
# _mark_filled
# ---------------------------------------------------------------------------


class TestMarkFilled:
    @pytest.mark.asyncio
    async def test_buy_updates_pending_and_inserts_trade_and_upserts_position(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        doc = _make_doc({"action": "buy", "price": 150.0, "shares": 10})
        await tracker._mark_filled(doc)

        pending.update_one.assert_called_once()
        trades.insert_one.assert_called_once()
        insert_args = trades.insert_one.call_args[0][0]
        assert insert_args["symbol"] == "AAPL"
        assert insert_args["action"] == "buy"
        assert insert_args["price"] == 150.0
        assert insert_args["shares"] == 10

        positions.update_one.assert_called_once()
        upsert_args = positions.update_one.call_args
        assert upsert_args[0][0] == {"symbol": "AAPL"}
        assert upsert_args[0][1]["$set"]["entryPrice"] == 150.0

    @pytest.mark.asyncio
    async def test_sell_deletes_position(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        doc = _make_doc({"action": "sell"})
        await tracker._mark_filled(doc)

        pending.update_one.assert_called_once()
        trades.insert_one.assert_called_once()
        positions.delete_one.assert_called_once_with({"symbol": "AAPL"})




# ---------------------------------------------------------------------------
# _cancel
# ---------------------------------------------------------------------------


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancels_order_and_updates_status(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        doc = _make_doc()
        await tracker._cancel(doc)

        tracker.broker.cancel_order.assert_called_once_with("ord-001")
        pending.update_one.assert_called_once()
        args = pending.update_one.call_args[0][1]
        assert args["$set"]["status"] == "timeout"
        assert "max_pending_age exceeded" in args["$set"]["error"]

    @pytest.mark.asyncio
    async def test_cancel_error_logged_does_not_raise(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        tracker.broker.cancel_order.side_effect = RuntimeError("API down")
        doc = _make_doc()
        await tracker._cancel(doc)

        pending.update_one.assert_called_once()


# ---------------------------------------------------------------------------
# _mark_failed
# ---------------------------------------------------------------------------


class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_updates_status_to_failed(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        doc = _make_doc()
        await tracker._mark_failed(doc, "insufficient margin")

        pending.update_one.assert_called_once()
        args = pending.update_one.call_args[0][1]
        assert args["$set"]["status"] == "failed"
        assert args["$set"]["error"] == "insufficient margin"


# ---------------------------------------------------------------------------
# _check_pending
# ---------------------------------------------------------------------------


class TestCheckPending:
    @pytest.mark.asyncio
    async def test_filled_order_calls_mark_filled(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        doc = _make_doc()
        pending.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("filled", "filled"))

        with patch.object(tracker, "_mark_filled", new_callable=AsyncMock) as mock_mark:
            await tracker._check_pending()
            mock_mark.assert_called_once_with(doc)

    @pytest.mark.asyncio
    async def test_cancelled_order_calls_mark_failed(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        doc = _make_doc()
        pending.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("cancelled", "cancelled"))

        with patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail:
            await tracker._check_pending()
            mock_fail.assert_called_once_with(doc, "cancelled")

    @pytest.mark.asyncio
    async def test_pending_order_updates_next_check_at(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        doc = _make_doc()
        pending.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("pending", "new"))

        await tracker._check_pending()

        pending.update_one.assert_called_once()
        args = pending.update_one.call_args[0][1]
        assert "$set" in args
        assert "next_check_at" in args["$set"]

    @pytest.mark.asyncio
    async def test_aged_order_calls_cancel(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        old = utcnow() - timedelta(seconds=400)
        doc = _make_doc({"placed_at": old})
        pending.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("filled", "filled"))

        with patch.object(tracker, "_cancel", new_callable=AsyncMock) as mock_cancel:
            await tracker._check_pending()
            mock_cancel.assert_called_once_with(doc)

    @pytest.mark.asyncio
    async def test_not_implemented_error_skips(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        doc = _make_doc()
        pending.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(side_effect=NotImplementedError())

        with (patch.object(tracker, "_mark_filled", new_callable=AsyncMock) as mock_fill,
              patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail):
            await tracker._check_pending()
            mock_fill.assert_not_called()
            mock_fail.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_during_check_retries_later(self, mock_mongo):
        tracker, pending, trades, positions = mock_mongo
        doc = _make_doc()
        pending.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(side_effect=RuntimeError("timeout"))

        await tracker._check_pending()

        pending.update_one.assert_called_once()
        args = pending.update_one.call_args[0][1]
        assert "$set" in args
        assert "next_check_at" in args["$set"]
        assert "retry_count" in args["$set"]


# ---------------------------------------------------------------------------
# Full lifecycle integration
# ---------------------------------------------------------------------------


class TestTrackerLifecycle:
    @pytest.mark.asyncio
    async def test_run_interval(self):
        from src.common.order_tracker import OrderTracker

        bus = MagicMock()
        broker = MagicMock()
        collection = MagicMock()
        tracker = OrderTracker(bus, broker, check_interval=0.01, collection=collection)

        with patch.object(tracker, "_check_pending") as mock_check:
            task = asyncio.create_task(tracker.run())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, RuntimeError):
                pass

            assert mock_check.called
