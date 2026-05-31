import logging
import os
import time
from urllib.parse import quote_plus

from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

logger = logging.getLogger(__name__)
_client = None

def _build_uri():
    MONGODB_URI = os.getenv('MONGODB_URI', '')
    MONGODB_USER = os.getenv('MONGODB_USER', '')
    MONGODB_PASS = os.getenv('MONGODB_PASS', '')

    if MONGODB_URI and not MONGODB_URI.startswith("mongodb://") and not MONGODB_URI.startswith("mongodb+srv://"):
        MONGODB_CLUSTERNAME = os.getenv('MONGODB_CLUSTERNAME', '')
        if not all([MONGODB_USER, MONGODB_PASS, MONGODB_CLUSTERNAME]):
            raise ValueError("MONGODB_USER, MONGODB_PASS, and MONGODB_CLUSTERNAME are required for Atlas SRV.")
        return f"mongodb+srv://{quote_plus(MONGODB_USER)}:{quote_plus(MONGODB_PASS)}@{MONGODB_URI}/?appName={MONGODB_CLUSTERNAME}"
    if MONGODB_URI:
        return MONGODB_URI
    raise ValueError("Set MONGODB_URI (or MONGODB_URI + USER + PASS + CLUSTERNAME for Atlas SRV).")


def get_mongo_client(max_retries: int = 3, retry_delay: float = 2.0):
    global _client
    if _client is not None:
        return _client

    uri = _build_uri()

    for attempt in range(1, max_retries + 1):
        client = MongoClient(uri, server_api=ServerApi('1'))
        try:
            client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            _client = client
            return _client
        except Exception as e:
            logger.warning("MongoDB ping attempt %d/%d failed: %s", attempt, max_retries, e)
            if attempt < max_retries:
                time.sleep(retry_delay)
            else:
                client.close()
                raise ConnectionError(f"Failed to connect to MongoDB after {max_retries} attempts: {e}") from e



