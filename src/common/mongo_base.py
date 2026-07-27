"""Shared MongoDB connection mixin for all Mongo*Store classes.

Eliminates the duplicated __init__ boilerplate across
MongoPositionStore, MongoOrderStore, MongoLogStore, MongoHeartbeatStore.

Usage:
    class MongoPositionStore(BasePositionStore, MongoStoreBase):
        collection = COLLECTION_POSITIONS
"""
import logging

logger = logging.getLogger(__name__)


class MongoStoreBase:
    """Shared MongoDB connection logic for all stores.

    Subclasses set ``collection`` as a class attribute to specify
    which MongoDB collection to bind to.  The ``__init__`` resolves
    the database connection via ``get_db()`` if no ``db`` is provided.
    """

    collection: str = ""

    def __init__(self, db=None, collection: str | None = None):
        try:
            if db is None:
                from src.data.utils.db_helper import get_db
                db = get_db()
            self._col = db[collection or self.collection]
        except Exception:
            logger.exception("Failed to connect to MongoDB for %s", self.__class__.__name__)
            raise
