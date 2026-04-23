"""Tests for PositionStore — mocked Redis, no real connection needed."""
from unittest.mock import MagicMock, patch
from src.common.position_store import PositionStore


class TestPositionStore:
    def _make_store(self):
        with patch("src.common.position_store.redis.Redis") as mock_cls:
            mock_redis = MagicMock()
            mock_cls.return_value = mock_redis
            store = PositionStore()
            return store, mock_redis

    def test_set_positions(self):
        store, mock_redis = self._make_store()
        store.set_positions({"AAPL": 50, "NVDA": 30})
        mock_redis.set.assert_called_once()
        key, value = mock_redis.set.call_args[0]
        assert key == "eontrading:positions"
        assert "AAPL" in value
        assert "NVDA" in value

    def test_get_positions_with_data(self):
        store, mock_redis = self._make_store()
        mock_redis.get.return_value = '{"AAPL": 50, "TSLA": 20}'
        positions = store.get_positions()
        assert positions == {"AAPL": 50, "TSLA": 20}

    def test_get_positions_empty(self):
        store, mock_redis = self._make_store()
        mock_redis.get.return_value = None
        positions = store.get_positions()
        assert positions == {}

    def test_set_then_get_roundtrip(self):
        store, mock_redis = self._make_store()
        # Simulate Redis storing the value
        stored = {}
        mock_redis.set.side_effect = lambda k, v: stored.update({k: v})
        mock_redis.get.side_effect = lambda k: stored.get(k)

        store.set_positions({"META": 10})
        result = store.get_positions()
        assert result == {"META": 10}

    def test_overwrite_positions(self):
        store, mock_redis = self._make_store()
        stored = {}
        mock_redis.set.side_effect = lambda k, v: stored.update({k: v})
        mock_redis.get.side_effect = lambda k: stored.get(k)

        store.set_positions({"AAPL": 50})
        store.set_positions({"AAPL": 50, "TSLA": 20})
        result = store.get_positions()
        assert result == {"AAPL": 50, "TSLA": 20}

    def test_clear_positions(self):
        store, mock_redis = self._make_store()
        stored = {}
        mock_redis.set.side_effect = lambda k, v: stored.update({k: v})
        mock_redis.get.side_effect = lambda k: stored.get(k)

        store.set_positions({"AAPL": 50})
        store.set_positions({})
        result = store.get_positions()
        assert result == {}
