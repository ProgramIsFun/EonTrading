"""Tests for MongoLogStore — mocked MongoDB, no real connection needed."""
from unittest.mock import MagicMock, patch

from src.common.log_store import MongoLogStore


def _make_store():
    """Create a MongoLogStore with mocked MongoDB collection."""
    mock_col = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)
    with patch("src.data.utils.db_helper.get_db", return_value=mock_db):
        store = MongoLogStore()
    return store, mock_col


class TestMongoLogStore:
    def test_init_connects_to_default_collection(self):
        store, mock_col = _make_store()
        assert store._col is mock_col

    def test_init_calls_get_db_when_db_is_none(self):
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        with patch("src.data.utils.db_helper.get_db", return_value=mock_db) as mock_get_db:
            MongoLogStore()
        mock_get_db.assert_called_once()

    def test_init_uses_provided_db(self):
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        store = MongoLogStore(db=mock_db)
        assert store._col is mock_col

    def test_find_logs_no_filters(self):
        store, mock_col = _make_store()
        mock_col.find.return_value.sort.return_value.limit.return_value = [
            {"message": "hello"},
        ]
        result = store.find_logs()
        mock_col.find.assert_called_once_with({}, {"_id": 0})
        assert len(result) == 1

    def test_find_logs_by_logger_name(self):
        store, mock_col = _make_store()
        mock_col.find.return_value.sort.return_value.limit.return_value = []
        store.find_logs(logger_name="src.live")
        expected_q = {"logger": {"$regex": "^src.live"}}
        mock_col.find.assert_called_once_with(expected_q, {"_id": 0})

    def test_find_logs_by_level(self):
        store, mock_col = _make_store()
        mock_col.find.return_value.sort.return_value.limit.return_value = []
        store.find_logs(level="ERROR")
        mock_col.find.assert_called_once_with({"level": "ERROR"}, {"_id": 0})

    def test_find_logs_by_logger_and_level(self):
        store, mock_col = _make_store()
        mock_col.find.return_value.sort.return_value.limit.return_value = []
        store.find_logs(logger_name="src.api", level="warning")
        expected_q = {
            "logger": {"$regex": "^src.api"},
            "level": "WARNING",
        }
        mock_col.find.assert_called_once_with(expected_q, {"_id": 0})

    def test_find_logs_limit(self):
        store, mock_col = _make_store()
        store.find_logs(limit=25)
        mock_col.find.return_value.sort.return_value.limit.assert_called_once_with(25)

    def test_find_logs_sorts_by_timestamp_desc(self):
        store, mock_col = _make_store()
        store.find_logs()
        mock_col.find.return_value.sort.assert_called_once_with("timestamp", -1)
