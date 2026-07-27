"""Tests for MongoHeartbeatStore — mocked MongoDB, no real connection needed."""
from unittest.mock import MagicMock, patch

from src.common.heartbeat import MongoHeartbeatStore


def _make_store():
    """Create a MongoHeartbeatStore with mocked MongoDB collection."""
    mock_col = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)
    with patch("src.data.utils.db_helper.get_db", return_value=mock_db):
        store = MongoHeartbeatStore()
    return store, mock_col


class TestMongoHeartbeatStore:
    def test_init_connects_to_collection(self):
        store, mock_col = _make_store()
        assert store._col is mock_col

    def test_init_calls_get_db_when_db_is_none(self):
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        with patch("src.data.utils.db_helper.get_db", return_value=mock_db) as mock_get_db:
            MongoHeartbeatStore()
        mock_get_db.assert_called_once()

    def test_init_uses_provided_db(self):
        mock_col = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        store = MongoHeartbeatStore(db=mock_db)
        assert store._col is mock_col

    def test_init_sets_col_none_on_failure(self):
        with patch("src.data.utils.db_helper.get_db", side_effect=RuntimeError("connection refused")):
            store = MongoHeartbeatStore()
        assert store._col is None

    def test_beat_writes_heartbeat(self):
        store, mock_col = _make_store()
        store.beat("analyzer")
        mock_col.update_one.assert_called_once()
        args = mock_col.update_one.call_args
        assert args[0][0] == {"component": "analyzer"}
        assert args[0][1]["$set"]["component"] == "analyzer"
        assert "lastBeat" in args[0][1]["$set"]
        assert "host" in args[0][1]["$set"]
        assert "pid" in args[0][1]["$set"]
        assert args[1]["upsert"] is True

    def test_beat_includes_metadata(self):
        store, mock_col = _make_store()
        store.beat("trader", metadata={"version": "1.0"})
        args = mock_col.update_one.call_args
        assert args[0][1]["$set"]["version"] == "1.0"

    def test_beat_noop_when_col_is_none(self):
        store = MongoHeartbeatStore.__new__(MongoHeartbeatStore)
        store._col = None
        store.beat("analyzer")
        # No error, just silently returns
