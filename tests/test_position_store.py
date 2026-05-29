"""Tests for PositionStore — mocked MongoDB, no real connection needed."""
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.common.clock import utcnow
from src.common.position_store import PositionStore


def _make_store():
    """Create a PositionStore with mocked MongoDB collection."""
    mock_col = MagicMock()
    mock_col.update_one = AsyncMock()
    mock_col.delete_one = AsyncMock()
    mock_col.delete_many = AsyncMock()
    # find() returns a cursor whose .to_list() is awaitable
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock()
    mock_col.find.return_value = mock_cursor
    with patch("src.common.position_store.get_mongo_client") as mock_client:
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_col)
        mock_client.return_value.__getitem__ = MagicMock(return_value=mock_db)
        store = PositionStore()
        store._col = mock_col
    return store, mock_col


class TestPositionStore:
    @pytest.mark.asyncio
    async def test_open_position(self):
        store, mock_col = _make_store()
        now = utcnow()
        await store.open_position("AAPL", now)
        mock_col.update_one.assert_awaited_once()
        args = mock_col.update_one.call_args
        assert args[0][0] == {"symbol": "AAPL"}
        assert now.isoformat() in str(args[0][1])

    @pytest.mark.asyncio
    async def test_close_position(self):
        store, mock_col = _make_store()
        await store.close_position("AAPL")
        mock_col.delete_one.assert_awaited_once_with({"symbol": "AAPL"})

    @pytest.mark.asyncio
    async def test_get_positions_with_data(self):
        store, mock_col = _make_store()
        now = utcnow()
        mock_col.find.return_value.to_list = AsyncMock(return_value=[
            {"symbol": "AAPL", "entryTime": now.isoformat()},
            {"symbol": "TSLA", "entryTime": now.isoformat()},
        ])
        positions = await store.get_positions()
        assert "AAPL" in positions
        assert "TSLA" in positions
        assert isinstance(positions["AAPL"], datetime)

    @pytest.mark.asyncio
    async def test_get_positions_empty(self):
        store, mock_col = _make_store()
        mock_col.find.return_value.to_list = AsyncMock(return_value=[])
        positions = await store.get_positions()
        assert positions == {}

    @pytest.mark.asyncio
    async def test_set_positions_upserts_and_deletes(self):
        store, mock_col = _make_store()
        now = utcnow()
        await store.set_positions({"AAPL": now, "NVDA": now})
        assert mock_col.update_one.await_count == 2
        mock_col.delete_many.assert_awaited_once()
        delete_filter = mock_col.delete_many.call_args[0][0]
        assert set(delete_filter["symbol"]["$nin"]) == {"AAPL", "NVDA"}

    @pytest.mark.asyncio
    async def test_set_positions_empty_clears_all(self):
        store, mock_col = _make_store()
        await store.set_positions({})
        mock_col.delete_many.assert_awaited_once_with({})
