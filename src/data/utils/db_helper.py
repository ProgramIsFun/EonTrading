import logging
import os
from urllib.parse import quote_plus

from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

logger = logging.getLogger(__name__)
_client = None

def get_mongo_client():
    global _client
    if _client is not None:
        return _client

    MONGODB_URI = os.getenv('MONGODB_URI', '')
    MONGODB_USER = os.getenv('MONGODB_USER', '')
    MONGODB_PASS = os.getenv('MONGODB_PASS', '')

    if MONGODB_URI and not MONGODB_URI.startswith("mongodb://") and not MONGODB_URI.startswith("mongodb+srv://"):
        # Atlas SRV mode — requires cluster name for appName
        MONGODB_CLUSTERNAME = os.getenv('MONGODB_CLUSTERNAME', '')
        if not all([MONGODB_USER, MONGODB_PASS, MONGODB_CLUSTERNAME]):
            raise ValueError("MONGODB_USER, MONGODB_PASS, and MONGODB_CLUSTERNAME are required for Atlas SRV.")
        uri = f"mongodb+srv://{quote_plus(MONGODB_USER)}:{quote_plus(MONGODB_PASS)}@{MONGODB_URI}/?appName={MONGODB_CLUSTERNAME}"
    elif MONGODB_URI:
        # Full URI mode (local or Atlas) — use as-is
        uri = MONGODB_URI
    else:
        raise ValueError("Set MONGODB_URI (or MONGODB_URI + USER + PASS + CLUSTERNAME for Atlas SRV).")

    client = MongoClient(uri, server_api=ServerApi('1'))

    try:
        client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        _client = client
        return _client
    except Exception as e:
        raise ConnectionError(f"Failed to connect to MongoDB: {e}") from e



