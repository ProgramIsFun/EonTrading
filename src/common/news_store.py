"""Shared news document builder — single place to define the MongoDB news schema."""
from src.common.clock import utcnow
from src.common.events import NewsEvent


def news_to_doc(event: NewsEvent, origin: str = "live") -> dict:
    """Convert a NewsEvent to a MongoDB document.

    Args:
        event: The news event to store.
        origin: 'live' (real-time watcher) or 'backfill' (historical import).
    """
    return {
        "source": event.source,
        "headline": event.headline,
        "timestamp": event.timestamp,
        "url": event.url,
        "body": event.body,
        "collected_at": utcnow().isoformat() + "Z",
        "origin": origin,
    }
