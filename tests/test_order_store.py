"""Tests for MongoOrderStore — mocked MongoDB, no real connection needed."""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.common.clock import utcnow
from src.common.order_store import MongoOrderStore


def _make_store():
    """Create a MongoOrderStore with mocked MongoDB collection."""
    mock_col = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)
    with patch("src.data.utils.db_helper.get_db", return_value=mock_db):
        store = MongoOrderStore()
    return store, mock_col


class TestMongoOrderStore:
    def test_init_connects_to_default_collection(self):
        store, mock_col = _make_store()
        assert store._col is mock_col

    def test_init_calls_get_db_when_db_is_none(self):
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        with patch("src.data.utils.db_helper.get_db", return_value=mock_db) as mock_get_db:
            MongoOrderStore()
        mock_get_db.assert_called_once()

    def test_init_uses_provided_db(self):
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        store = MongoOrderStore(db=mock_db)
        assert store._col is mock_col
        mock_db.__getitem__.assert_called_once()

    def test_init_uses_provided_collection_name(self):
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        store = MongoOrderStore(db=mock_db, collection="custom_orders")
        assert store._col is mock_col
        mock_db.__getitem__.assert_called_once_with("custom_orders")

    def test_insert(self):
        store, mock_col = _make_store()
        doc = {"symbol": "AAPL", "side": "buy", "shares": 10}
        store.insert(doc)
        mock_col.insert_one.assert_called_once_with(doc)

    def test_find_pending(self):
        store, mock_col = _make_store()
        now = utcnow()
        mock_col.find.return_value = [{"status": "pending", "symbol": "AAPL"}]
        result = store.find_pending(now)
        mock_col.find.assert_called_once()
        assert len(result) == 1
        assert result[0]["symbol"] == "AAPL"

    def test_mark_filled(self):
        store, mock_col = _make_store()
        fake_id = MagicMock()
        fill_time = utcnow()
        store.mark_filled(fake_id, fill_time)
        mock_col.update_one.assert_called_once()
        args = mock_col.update_one.call_args
        assert args[0][0] == {"_id": fake_id}
        assert args[0][1]["$set"]["status"] == "filled"
        assert args[0][1]["$set"]["filled_at"] == fill_time

    def test_mark_failed(self):
        store, mock_col = _make_store()
        fake_id = MagicMock()
        store.mark_failed(fake_id, "network timeout")
        args = mock_col.update_one.call_args
        assert args[0][1]["$set"]["status"] == "failed"
        assert args[0][1]["$set"]["error"] == "network timeout"

    def test_mark_timeout(self):
        store, mock_col = _make_store()
        fake_id = MagicMock()
        store.mark_timeout(fake_id, "order stale")
        args = mock_col.update_one.call_args
        assert args[0][1]["$set"]["status"] == "timeout"
        assert args[0][1]["$set"]["error"] == "order stale"
        assert "cancelled_at" in args[0][1]["$set"]

    def test_update_retry(self):
        store, mock_col = _make_store()
        fake_id = MagicMock()
        now = utcnow()
        next_check = now + timedelta(seconds=30)
        store.update_retry(fake_id, next_check, now, 2)
        args = mock_col.update_one.call_args
        assert args[0][1]["$set"]["next_check_at"] == next_check
        assert args[0][1]["$set"]["checked_at"] == now
        assert args[0][1]["$set"]["retry_count"] == 2

    def test_find_filled(self):
        store, mock_col = _make_store()
        mock_col.find.return_value.sort.return_value.limit.return_value = [
            {"symbol": "AAPL", "status": "filled"},
        ]
        result = store.find_filled(limit=50)
        mock_col.find.assert_called_once_with({"status": "filled"}, {"_id": 0})
        assert len(result) == 1

    def test_ensure_indexes(self):
        store, mock_col = _make_store()
        store.ensure_indexes()
        assert mock_col.create_index.call_count == 2
