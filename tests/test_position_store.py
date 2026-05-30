"""Tests for PositionStore — mocked MongoDB, no real connection needed."""
from datetime import datetime
from unittest.mock import MagicMock, patch

from src.common.clock import utcnow
from src.common.position_store import InMemoryPositionStore, PositionStore


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
        now = utcnow()
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
        now = utcnow()
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
        now = utcnow()
        store.set_positions({"AAPL": now, "NVDA": now})
        assert mock_col.update_one.call_count == 2
        mock_col.delete_many.assert_called_once()
        delete_filter = mock_col.delete_many.call_args[0][0]
        assert set(delete_filter["symbol"]["$nin"]) == {"AAPL", "NVDA"}

    def test_set_positions_empty_clears_all(self):
        store, mock_col = _make_store()
        store.set_positions({})
        mock_col.delete_many.assert_called_once_with({})


class TestInMemoryPositionStore:
    def test_open_and_get_position(self):
        store = InMemoryPositionStore()
        now = utcnow()
        store.open_position("AAPL", now, entry_price=150.0)
        positions = store.get_positions()
        assert "AAPL" in positions
        assert positions["AAPL"] == now

    def test_open_position_with_price(self):
        store = InMemoryPositionStore()
        store.open_position("AAPL", utcnow(), entry_price=150.0)
        prices = store.get_positions_with_prices()
        assert prices["AAPL"]["entryPrice"] == 150.0

    def test_close_position(self):
        store = InMemoryPositionStore()
        store.open_position("AAPL", utcnow())
        store.close_position("AAPL")
        assert store.get_positions() == {}

    def test_close_nonexistent_is_noop(self):
        store = InMemoryPositionStore()
        store.close_position("NEVER_OPENED")
        assert store.get_positions() == {}

    def test_get_positions_empty(self):
        store = InMemoryPositionStore()
        assert store.get_positions() == {}

    def test_get_positions_with_prices_empty(self):
        store = InMemoryPositionStore()
        assert store.get_positions_with_prices() == {}

    def test_get_positions_with_prices(self):
        store = InMemoryPositionStore()
        now = utcnow()
        store.open_position("AAPL", now, entry_price=150.0)
        store.open_position("TSLA", now, entry_price=300.0)
        prices = store.get_positions_with_prices()
        assert set(prices.keys()) == {"AAPL", "TSLA"}
        assert prices["AAPL"]["entryPrice"] == 150.0
        assert prices["TSLA"]["entryPrice"] == 300.0

    def test_set_positions(self):
        store = InMemoryPositionStore()
        now = utcnow()
        store.set_positions({"AAPL": now}, entry_prices={"AAPL": 150.0})
        assert "AAPL" in store.get_positions()
        assert store.get_positions_with_prices()["AAPL"]["entryPrice"] == 150.0

    def test_set_positions_empty(self):
        store = InMemoryPositionStore()
        store.open_position("AAPL", utcnow())
        store.set_positions({})
        assert store.get_positions() == {}

    def test_multiple_positions(self):
        store = InMemoryPositionStore()
        t1 = utcnow()
        store.open_position("AAPL", t1)
        store.open_position("TSLA", t1)
        store.open_position("GOOG", t1)
        assert len(store.get_positions()) == 3

    def test_close_one_of_many(self):
        store = InMemoryPositionStore()
        t1 = utcnow()
        store.open_position("AAPL", t1)
        store.open_position("TSLA", t1)
        store.close_position("AAPL")
        positions = store.get_positions()
        assert "AAPL" not in positions
        assert "TSLA" in positions
