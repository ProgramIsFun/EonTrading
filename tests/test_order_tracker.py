"""Tests for OrderTracker — mocked MongoDB, no real connection needed."""
import asyncio
from datetime import timedelta
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
    mock_orders = MagicMock()
    mock_stores = MagicMock()

    with patch("src.common.order_tracker.get_mongo_client") as m:
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(side_effect=lambda name: {
            "orders": mock_orders,
        }[name])
        m.return_value.__getitem__ = MagicMock(return_value=mock_db)

        tracker = _build_tracker(position_store=mock_stores)
        tracker._col = mock_orders

        yield tracker, mock_orders, mock_stores


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
    async def test_buy_updates_order_and_upserts_position_with_qty(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc({"action": "buy", "price": 150.0, "shares": 10})
        await tracker._mark_filled(doc)

        orders.update_one.assert_called_once()

        store.open_position.assert_called_once()
        open_args = store.open_position.call_args[0]
        assert open_args[0] == "AAPL"
        assert open_args[2] == 150.0  # entry_price
        assert open_args[3] == 10     # qty

    @pytest.mark.asyncio
    async def test_sell_deletes_position(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc({"action": "sell"})
        await tracker._mark_filled(doc)

        orders.update_one.assert_called_once()
        store.close_position.assert_called_once_with("AAPL")




# ---------------------------------------------------------------------------
# _cancel
# ---------------------------------------------------------------------------


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancels_order_and_updates_status(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc()
        await tracker._cancel(doc)

        tracker.broker.cancel_order.assert_called_once_with("ord-001")
        orders.update_one.assert_called_once()
        args = orders.update_one.call_args[0][1]
        assert args["$set"]["status"] == "timeout"
        assert "max_pending_age exceeded" in args["$set"]["error"]

    @pytest.mark.asyncio
    async def test_cancel_error_logged_does_not_raise(self, mock_mongo):
        tracker, orders, store = mock_mongo
        tracker.broker.cancel_order.side_effect = RuntimeError("API down")
        doc = _make_doc()
        await tracker._cancel(doc)

        orders.update_one.assert_called_once()


# ---------------------------------------------------------------------------
# _mark_failed
# ---------------------------------------------------------------------------


class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_updates_status_to_failed(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc()
        await tracker._mark_failed(doc, "insufficient margin")

        orders.update_one.assert_called_once()
        args = orders.update_one.call_args[0][1]
        assert args["$set"]["status"] == "failed"
        assert args["$set"]["error"] == "insufficient margin"


# ---------------------------------------------------------------------------
# _check_pending
# ---------------------------------------------------------------------------


class TestCheckPending:
    @pytest.mark.asyncio
    async def test_filled_order_calls_mark_filled(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc()
        orders.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("filled", "filled"))

        with patch.object(tracker, "_mark_filled", new_callable=AsyncMock) as mock_mark:
            await tracker._check_pending()
            mock_mark.assert_called_once_with(doc)

    @pytest.mark.asyncio
    async def test_cancelled_order_calls_mark_failed(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc()
        orders.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("cancelled", "cancelled"))

        with patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail:
            await tracker._check_pending()
            mock_fail.assert_called_once_with(doc, "cancelled")

    @pytest.mark.asyncio
    async def test_pending_order_updates_next_check_at(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc()
        orders.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("pending", "new"))

        await tracker._check_pending()

        orders.update_one.assert_called_once()
        args = orders.update_one.call_args[0][1]
        assert "$set" in args
        assert "next_check_at" in args["$set"]

    @pytest.mark.asyncio
    async def test_aged_order_calls_cancel(self, mock_mongo):
        tracker, orders, store = mock_mongo
        old = utcnow() - timedelta(seconds=400)
        doc = _make_doc({"placed_at": old})
        orders.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("filled", "filled"))

        with patch.object(tracker, "_cancel", new_callable=AsyncMock) as mock_cancel:
            await tracker._check_pending()
            mock_cancel.assert_called_once_with(doc)

    @pytest.mark.asyncio
    async def test_not_implemented_error_skips(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc()
        orders.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(side_effect=NotImplementedError())

        with (patch.object(tracker, "_mark_filled", new_callable=AsyncMock) as mock_fill,
              patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail):
            await tracker._check_pending()
            mock_fill.assert_not_called()
            mock_fail.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_during_check_retries_later(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc()
        orders.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(side_effect=RuntimeError("timeout"))

        await tracker._check_pending()

        tracker._col.update_one.assert_called_once()
        args = tracker._col.update_one.call_args[0][1]
        assert "$set" in args
        assert "next_check_at" in args["$set"]
        assert "retry_count" in args["$set"]

    @pytest.mark.asyncio
    async def test_failed_status_calls_mark_failed(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc()
        orders.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("failed", "insufficient margin"))

        with patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail:
            await tracker._check_pending()
            mock_fail.assert_called_once_with(doc, "insufficient margin")

    @pytest.mark.asyncio
    async def test_rejected_status_calls_mark_failed(self, mock_mongo):
        tracker, orders, store = mock_mongo
        doc = _make_doc()
        orders.find.return_value = iter([doc])

        tracker.broker.check_order = AsyncMock(return_value=("rejected", "risk limit"))

        with patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail:
            await tracker._check_pending()
            mock_fail.assert_called_once_with(doc, "risk limit")

    @pytest.mark.asyncio
    async def test_multiple_orders_processed(self, mock_mongo):
        tracker, orders, store = mock_mongo
        docs = [_make_doc({"_id": f"id-{i}", "order_id": f"ord-{i}"}) for i in range(3)]
        orders.find.return_value = iter(docs)

        tracker.broker.check_order = AsyncMock(return_value=("filled", "ok"))

        with patch.object(tracker, "_mark_filled", new_callable=AsyncMock) as mock_mark:
            await tracker._check_pending()
            assert mock_mark.call_count == 3


class TestEnsureIndexes:
    def test_indexes_created(self, mock_mongo):
        tracker, orders, store = mock_mongo
        # _ensure_indexes is called during OrderTracker.__init__
        assert orders.create_index.call_count >= 2
        # First call: compound index on [(status, 1), (next_check_at, 1)]
        first_keys = orders.create_index.call_args_list[0][0][0]
        assert isinstance(first_keys, list)
        key_names = [k for k, _ in first_keys]
        assert "status" in key_names
        assert "next_check_at" in key_names
        # Second call: single-field index on "placed_at" with TTL
        second_key = orders.create_index.call_args_list[1][0][0]
        assert second_key == "placed_at"
        assert orders.create_index.call_args_list[1][1].get("expireAfterSeconds") == 604800


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
        position_store = MagicMock()
        tracker = OrderTracker(bus, broker, check_interval=0.01, collection=collection,
                               position_store=position_store)

        with patch.object(tracker, "_check_pending") as mock_check:
            task = asyncio.create_task(tracker.run())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, RuntimeError):
                pass

            assert mock_check.called
