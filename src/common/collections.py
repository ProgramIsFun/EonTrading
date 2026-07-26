"""Centralized MongoDB collection names.

Swap this file (or individual constants) when migrating to a different database.

FUTURE: When cross-store transactions are needed (e.g., updating orders +
positions atomically), add a BaseTransactionManager ABC that yields sessions.
Each DB implementation (MongoTransactionManager, PostgresTransactionManager)
wraps its native transaction protocol. Store methods accept an optional
`session=` parameter so they participate in the caller's transaction.
"""
COLLECTION_ORDERS = "orders"
COLLECTION_NEWS = "news"
COLLECTION_POSITIONS = "positions"
COLLECTION_HEARTBEATS = "heartbeats"
COLLECTION_SEEN_URLS = "seen_urls"
COLLECTION_LOGS = "logs"
