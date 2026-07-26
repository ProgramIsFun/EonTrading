"""News store abstraction — BaseNewsStore defines the interface,
MongoNewsStore implements it with pymongo (two collections: news + seen_urls).

FUTURE: Add PostgresNewsStore, SqliteNewsStore, etc. by implementing
the same BaseNewsStore ABC.
"""
import logging
from abc import ABC, abstractmethod
from datetime import datetime

from src.common.collections import COLLECTION_NEWS, COLLECTION_SEEN_URLS

logger = logging.getLogger(__name__)


class BaseNewsStore(ABC):
    """Interface for news storage backends."""

    @abstractmethod
    def insert_news(self, doc: dict) -> None:
        """Insert a news article document."""
        pass

    @abstractmethod
    def find_news(self, query: dict = None, sort_by: str = "timestamp",
                  ascending: bool = True, limit: int = 100) -> list[dict]:
        """Query news articles with sort and limit."""
        pass

    @abstractmethod
    def count_news(self) -> int:
        """Return total number of news articles."""
        pass

    @abstractmethod
    def ensure_news_indexes(self) -> None:
        """Create indexes on the news collection (idempotent)."""
        pass

    @abstractmethod
    def is_seen(self, url: str) -> bool:
        """Check if a URL has been seen before."""
        pass

    @abstractmethod
    def mark_seen(self, url: str) -> None:
        """Record a URL as seen (idempotent)."""
        pass

    @abstractmethod
    def ensure_seen_indexes(self) -> None:
        """Create indexes on the seen_urls collection (idempotent)."""
        pass


class MongoNewsStore(BaseNewsStore):
    """MongoDB implementation using two collections: news + seen_urls."""

    def __init__(self, db=None):
        try:
            if db is None:
                from src.data.utils.db_helper import get_db
                db = get_db()
            self._news_col = db[COLLECTION_NEWS]
            self._seen_col = db[COLLECTION_SEEN_URLS]
        except Exception:
            logger.exception("Failed to connect to MongoDB for NewsStore")
            raise

    def insert_news(self, doc: dict) -> None:
        self._news_col.insert_one(doc)

    def find_news(self, query: dict = None, sort_by: str = "timestamp",
                  ascending: bool = True, limit: int = 100) -> list[dict]:
        q = query or {}
        cursor = self._news_col.find(q, {"_id": 0}).sort(sort_by, 1 if ascending else -1)
        if limit:
            cursor = cursor.limit(limit)
        return list(cursor)

    def count_news(self) -> int:
        return self._news_col.count_documents({})

    def ensure_news_indexes(self) -> None:
        self._news_col.create_index("url", unique=True, sparse=True)

    def is_seen(self, url: str) -> bool:
        if not url:
            return False
        return self._seen_col.find_one({"url": url}) is not None

    def mark_seen(self, url: str) -> None:
        if url:
            self._seen_col.insert_one({"url": url})

    def ensure_seen_indexes(self) -> None:
        self._seen_col.create_index("url", unique=True)


def news_to_doc(event, origin: str = "live") -> dict:
    """Convert a NewsEvent to a MongoDB document."""
    from src.common.clock import utcnow
    return {
        "source": event.source,
        "headline": event.headline,
        "timestamp": event.timestamp,
        "url": event.url,
        "body": event.body,
        "collected_at": utcnow().isoformat() + "Z",
        "origin": origin,
    }
