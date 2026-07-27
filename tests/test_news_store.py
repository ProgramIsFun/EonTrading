"""Tests for MongoNewsStore — mocked MongoDB, no real connection needed."""
from unittest.mock import MagicMock, patch

from src.common.news_store import MongoNewsStore, news_to_doc


def _make_store():
    """Create a MongoNewsStore with mocked MongoDB collections."""
    mock_news_col = MagicMock()
    mock_seen_col = MagicMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(side_effect=lambda name: {
        "news": mock_news_col,
        "seen_urls": mock_seen_col,
    }[name])
    with patch("src.data.utils.db_helper.get_db", return_value=mock_db):
        store = MongoNewsStore()
    return store, mock_news_col, mock_seen_col


class TestMongoNewsStore:
    def test_init_connects_to_collections(self):
        store, mock_news, mock_seen = _make_store()
        assert store._news_col is mock_news
        assert store._seen_col is mock_seen

    def test_init_calls_get_db_when_db_is_none(self):
        mock_news_col = MagicMock()
        mock_seen_col = MagicMock()
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(side_effect=lambda name: {
            "news": mock_news_col, "seen_urls": mock_seen_col,
        }[name])
        with patch("src.data.utils.db_helper.get_db", return_value=mock_db) as mock_get_db:
            MongoNewsStore()
        mock_get_db.assert_called_once()

    def test_insert_news(self):
        store, mock_news, _ = _make_store()
        doc = {"headline": "AAPL up 5%", "source": "finnhub"}
        store.insert_news(doc)
        mock_news.insert_one.assert_called_once_with(doc)

    def test_find_news_no_query(self):
        store, mock_news, _ = _make_store()
        mock_news.find.return_value.sort.return_value.limit.return_value = [
            {"headline": "AAPL up 5%"},
        ]
        result = store.find_news()
        mock_news.find.assert_called_once()
        assert len(result) == 1

    def test_find_news_with_query(self):
        store, mock_news, _ = _make_store()
        mock_news.find.return_value.sort.return_value.limit.return_value = []
        query = {"source": "finnhub"}
        store.find_news(query=query)
        mock_news.find.assert_called_once_with(query, {"_id": 0})

    def test_find_news_sort_ascending(self):
        store, mock_news, _ = _make_store()
        store.find_news(sort_by="timestamp", ascending=True)
        mock_news.find.return_value.sort.assert_called_once_with("timestamp", 1)

    def test_find_news_sort_descending(self):
        store, mock_news, _ = _make_store()
        store.find_news(sort_by="timestamp", ascending=False)
        mock_news.find.return_value.sort.assert_called_once_with("timestamp", -1)

    def test_find_news_limit(self):
        store, mock_news, _ = _make_store()
        store.find_news(limit=10)
        mock_news.find.return_value.sort.return_value.limit.assert_called_once_with(10)

    def test_find_news_limit_zero(self):
        store, mock_news, _ = _make_store()
        store.find_news(limit=0)
        mock_news.find.return_value.sort.return_value.limit.assert_not_called()

    def test_count_news(self):
        store, mock_news, _ = _make_store()
        mock_news.count_documents.return_value = 42
        assert store.count_news() == 42
        mock_news.count_documents.assert_called_once_with({})

    def test_is_seen_true(self):
        store, _, mock_seen = _make_store()
        mock_seen.find_one.return_value = {"url": "http://example.com"}
        assert store.is_seen("http://example.com") is True

    def test_is_seen_false(self):
        store, _, mock_seen = _make_store()
        mock_seen.find_one.return_value = None
        assert store.is_seen("http://example.com") is False

    def test_is_seen_empty_url(self):
        store, _, mock_seen = _make_store()
        assert store.is_seen("") is False
        assert store.is_seen(None) is False
        mock_seen.find_one.assert_not_called()

    def test_mark_seen(self):
        store, _, mock_seen = _make_store()
        store.mark_seen("http://example.com")
        mock_seen.insert_one.assert_called_once_with({"url": "http://example.com"})

    def test_mark_seen_empty_url(self):
        store, _, mock_seen = _make_store()
        store.mark_seen("")
        mock_seen.insert_one.assert_not_called()

    def test_ensure_news_indexes(self):
        store, mock_news, _ = _make_store()
        store.ensure_news_indexes()
        mock_news.create_index.assert_called_once_with("url", unique=True, sparse=True)

    def test_ensure_seen_indexes(self):
        store, _, mock_seen = _make_store()
        store.ensure_seen_indexes()
        mock_seen.create_index.assert_called_once_with("url", unique=True)


class TestNewsToDoc:
    def test_news_to_doc_basic(self):
        mock_event = MagicMock()
        mock_event.source = "finnhub"
        mock_event.headline = "AAPL up 5%"
        mock_event.timestamp = "2025-01-01T00:00:00"
        mock_event.url = "http://example.com"
        mock_event.body = "Apple stock rose."
        doc = news_to_doc(mock_event, origin="live")
        assert doc["source"] == "finnhub"
        assert doc["headline"] == "AAPL up 5%"
        assert doc["origin"] == "live"
        assert doc["url"] == "http://example.com"
        assert "collected_at" in doc
