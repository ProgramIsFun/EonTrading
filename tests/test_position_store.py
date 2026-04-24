"""Tests for PositionStore — mocked MongoDB, no real connection needed."""
from unittest.mock import MagicMock, patch
from datetime import datetime
from src.common.position_store import PositionStore


def _make_store():
    """Create a PositionStore with mocked MongoDB collection."""
    mock_col = MagicMock()
    with patch("src.common.position_store.get_mongo_client") as mock_client:
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        mock_client.return_value.__getitem__ = MagicMock(return_value=mock_db)
        store = PositionStore()
        store._col = mock_col
    return store, mock_col


class TestPositionStore:
    def test_open_position(self):
        store, mock_col = _make_store()
        now = datetime.utcnow()
        store.open_position("AAPL", now)
        mock_col.update_one.assert_called_once()
        args = mock_col.update_one.call_args
        assert args[0][0] == {"symbol": "AAPL"}
        assert now.isoformat() in str(args[0][1])

    def test_close_position(self):
        store, mock_col = _make_store()
        store.close_position("AAPL")
        mock_col.delete_one.assert_called_once_with({"symbol": "AAPL"})

    def test_get_positions_with_data(self):
        store, mock_col = _make_store()
        now = datetime.utcnow()
        mock_col.find.return_value = [
            {"symbol": "AAPL", "entryTime": now.isoformat()},
            {"symbol": "TSLA", "entryTime": now.isoformat()},
        ]
        positions = store.get_positions()
        assert "AAPL" in positions
        assert "TSLA" in positions
        assert isinstance(positions["AAPL"], datetime)

    def test_get_positions_empty(self):
        store, mock_col = _make_store()
        mock_col.find.return_value = []
        positions = store.get_positions()
        assert positions == {}

    def test_set_positions_upserts_and_deletes(self):
        store, mock_col = _make_store()
        now = datetime.utcnow()
        store.set_positions({"AAPL": now, "NVDA": now})
        assert mock_col.update_one.call_count == 2
        mock_col.delete_many.assert_called_once()
        delete_filter = mock_col.delete_many.call_args[0][0]
        assert set(delete_filter["symbol"]["$nin"]) == {"AAPL", "NVDA"}

    def test_set_positions_empty_clears_all(self):
        store, mock_col = _make_store()
        store.set_positions({})
        mock_col.delete_many.assert_called_once_with({})
