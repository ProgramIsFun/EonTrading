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

    # Load environment variables
    MONGODB_URI = os.getenv('MONGODB_URI')
    MONGODB_USER = os.getenv('MONGODB_USER')
    MONGODB_PASS = os.getenv('MONGODB_PASS')
    MONGODB_CLUSTERNAME = os.getenv('MONGODB_CLUSTERNAME')

    # Validate environment variables
    if not all([MONGODB_URI, MONGODB_USER, MONGODB_PASS, MONGODB_CLUSTERNAME]):
        raise ValueError("Missing one or more required MongoDB environment variables.")

    # URL-encode user/pass to handle special characters (@, :, /, %, etc.)
    uri = f"mongodb+srv://{quote_plus(MONGODB_USER)}:{quote_plus(MONGODB_PASS)}@{MONGODB_URI}/?appName={MONGODB_CLUSTERNAME}"

    # Create a new client
    client = MongoClient(uri, server_api=ServerApi('1'))

    # Send a ping to confirm a successful connection
    try:
        client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        _client = client
        return _client
    except Exception as e:
        raise ConnectionError(f"Failed to connect to MongoDB: {e}") from e


def get_symbols_list():
    """Return all documents from the symbols collection."""
    client = get_mongo_client()
    db = client['EonTradingDB']
    return list(db['symbols'].find({}))


# Backward compat alias
getSymbolsList = get_symbols_list
