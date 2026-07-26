"""Tests for OrderTracker — mocked store, no real connection needed."""
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.common.clock import utcnow
from src.common.events import TradeEvent
from src.live.brokers.broker import FillStatus


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
    mock_store = MagicMock()
    mock_position_store = MagicMock()

    with patch("src.common.order_tracker.MongoOrderStore", return_value=mock_store), \
         patch("src.common.order_tracker.PositionStore", return_value=mock_position_store):
        from src.common.order_tracker import OrderTracker
        bus = MagicMock()
        broker = MagicMock()
        tracker = OrderTracker(bus, broker)

        yield tracker, mock_store, mock_position_store


# ---------------------------------------------------------------------------
# _mark_filled
# ---------------------------------------------------------------------------


class TestMarkFilled:
    @pytest.mark.asyncio
    async def test_buy_updates_order_and_upserts_position_with_qty(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc({"action": "buy", "price": 150.0, "shares": 10})
        fill = FillStatus(status="filled", filled_qty=10, filled_price=150.0)
        await tracker._mark_filled(doc, fill)

        store.mark_filled.assert_called_once()

        pos_store.open_position.assert_called_once()
        open_args = pos_store.open_position.call_args[0]
        assert open_args[0] == "AAPL"
        assert open_args[2] == 150.0  # entry_price
        assert open_args[3] == 10     # qty

    @pytest.mark.asyncio
    async def test_sell_deletes_position(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc({"action": "sell"})
        fill = FillStatus(status="filled", filled_qty=10, filled_price=150.0)
        await tracker._mark_filled(doc, fill)

        store.mark_filled.assert_called_once()
        pos_store.close_position.assert_called_once_with("AAPL")

    @pytest.mark.asyncio
    async def test_uses_fill_price_over_order_price(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc({"action": "buy", "price": 150.0, "shares": 10})
        fill = FillStatus(status="filled", filled_qty=10, filled_price=155.0)
        await tracker._mark_filled(doc, fill)

        open_args = pos_store.open_position.call_args[0]
        assert open_args[2] == 155.0  # fill_price wins over doc price

    @pytest.mark.asyncio
    async def test_falls_back_to_doc_price_when_fill_price_zero(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc({"action": "buy", "price": 150.0, "shares": 10})
        fill = FillStatus(status="filled", filled_qty=10, filled_price=0.0)
        await tracker._mark_filled(doc, fill)

        open_args = pos_store.open_position.call_args[0]
        assert open_args[2] == 150.0  # falls back to doc price


# ---------------------------------------------------------------------------
# _cancel
# ---------------------------------------------------------------------------


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancels_order_and_updates_status(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc()
        await tracker._cancel(doc)

        tracker.broker.cancel_order.assert_called_once_with("ord-001")
        store.mark_timeout.assert_called_once_with("abc123", "max_pending_age exceeded")

    @pytest.mark.asyncio
    async def test_cancel_error_logged_does_not_raise(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        tracker.broker.cancel_order.side_effect = RuntimeError("API down")
        doc = _make_doc()
        await tracker._cancel(doc)

        store.mark_timeout.assert_called_once()


# ---------------------------------------------------------------------------
# _mark_failed
# ---------------------------------------------------------------------------


class TestMarkFailed:
    @pytest.mark.asyncio
    async def test_updates_status_to_failed(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc()
        await tracker._mark_failed(doc, "insufficient margin")

        store.mark_failed.assert_called_once_with("abc123", "insufficient margin")


# ---------------------------------------------------------------------------
# _check_pending
# ---------------------------------------------------------------------------


class TestCheckPending:
    @pytest.mark.asyncio
    async def test_filled_order_calls_mark_filled(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc()
        store.find_pending.return_value = [doc]

        tracker.broker.check_order = AsyncMock(return_value=FillStatus(status="filled", filled_qty=10, filled_price=150.0))

        with patch.object(tracker, "_mark_filled", new_callable=AsyncMock) as mock_mark:
            await tracker._check_pending()
            mock_mark.assert_called_once()
            assert mock_mark.call_args[0][0] == doc
            assert isinstance(mock_mark.call_args[0][1], FillStatus)

    @pytest.mark.asyncio
    async def test_cancelled_order_calls_mark_failed(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc()
        store.find_pending.return_value = [doc]

        tracker.broker.check_order = AsyncMock(return_value=FillStatus(status="cancelled", reason="user cancel"))

        with patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail:
            await tracker._check_pending()
            mock_fail.assert_called_once_with(doc, "user cancel")

    @pytest.mark.asyncio
    async def test_pending_order_updates_next_check_at(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc()
        store.find_pending.return_value = [doc]

        tracker.broker.check_order = AsyncMock(return_value=FillStatus(status="pending"))

        await tracker._check_pending()

        store.update_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_aged_order_calls_cancel(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        old = utcnow() - timedelta(seconds=400)
        doc = _make_doc({"placed_at": old})
        store.find_pending.return_value = [doc]

        tracker.broker.check_order = AsyncMock(return_value=FillStatus(status="filled", filled_qty=10, filled_price=150.0))

        with patch.object(tracker, "_cancel", new_callable=AsyncMock) as mock_cancel:
            await tracker._check_pending()
            mock_cancel.assert_called_once_with(doc)

    @pytest.mark.asyncio
    async def test_not_implemented_error_skips(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc()
        store.find_pending.return_value = [doc]

        tracker.broker.check_order = AsyncMock(side_effect=NotImplementedError())

        with (patch.object(tracker, "_mark_filled", new_callable=AsyncMock) as mock_fill,
              patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail):
            await tracker._check_pending()
            mock_fill.assert_not_called()
            mock_fail.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_during_check_retries_later(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc()
        store.find_pending.return_value = [doc]

        tracker.broker.check_order = AsyncMock(side_effect=RuntimeError("timeout"))

        await tracker._check_pending()

        store.update_retry.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_status_calls_mark_failed(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc()
        store.find_pending.return_value = [doc]

        tracker.broker.check_order = AsyncMock(return_value=FillStatus(status="failed", reason="insufficient margin"))

        with patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail:
            await tracker._check_pending()
            mock_fail.assert_called_once_with(doc, "insufficient margin")

    @pytest.mark.asyncio
    async def test_rejected_status_calls_mark_failed(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc()
        store.find_pending.return_value = [doc]

        tracker.broker.check_order = AsyncMock(return_value=FillStatus(status="rejected", reason="risk limit"))

        with patch.object(tracker, "_mark_failed", new_callable=AsyncMock) as mock_fail:
            await tracker._check_pending()
            mock_fail.assert_called_once_with(doc, "risk limit")

    @pytest.mark.asyncio
    async def test_partial_fill_does_not_update_position(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        doc = _make_doc({"shares": 10})
        store.find_pending.return_value = [doc]

        tracker.broker.check_order = AsyncMock(return_value=FillStatus(status="filled", filled_qty=3, filled_price=150.0))

        with patch.object(tracker, "_mark_filled", new_callable=AsyncMock) as mock_fill:
            await tracker._check_pending()
            mock_fill.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_orders_processed(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        docs = [_make_doc({"_id": f"id-{i}", "order_id": f"ord-{i}"}) for i in range(3)]
        store.find_pending.return_value = docs

        tracker.broker.check_order = AsyncMock(return_value=FillStatus(status="filled", filled_qty=10, filled_price=150.0))

        with patch.object(tracker, "_mark_filled", new_callable=AsyncMock) as mock_mark:
            await tracker._check_pending()
            assert mock_mark.call_count == 3


class TestEnsureIndexes:
    def test_indexes_created(self, mock_mongo):
        tracker, store, pos_store = mock_mongo
        store.ensure_indexes.assert_called_once()


# ---------------------------------------------------------------------------
# Full lifecycle integration
# ---------------------------------------------------------------------------


class TestTrackerLifecycle:
    @pytest.mark.asyncio
    async def test_run_interval(self):
        mock_store = MagicMock()
        mock_position_store = MagicMock()

        with patch("src.common.order_tracker.MongoOrderStore", return_value=mock_store), \
             patch("src.common.order_tracker.PositionStore", return_value=mock_position_store):
            from src.common.order_tracker import OrderTracker
            bus = MagicMock()
            broker = MagicMock()
            tracker = OrderTracker(bus, broker, check_interval=0.01)

        with patch.object(tracker, "_check_pending") as mock_check:
            task = asyncio.create_task(tracker.run())
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, RuntimeError):
                pass

            assert mock_check.called
