"""MongoDB connection singleton — returns an AsyncIOMotorClient."""
import logging
import os
from urllib.parse import quote_plus

from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)
_client = None


def get_mongo_client():
    global _client
    if _client is not None:
        return _client

    MONGODB_URI = os.getenv('MONGODB_URI')
    MONGODB_USER = os.getenv('MONGODB_USER')
    MONGODB_PASS = os.getenv('MONGODB_PASS')
    MONGODB_CLUSTERNAME = os.getenv('MONGODB_CLUSTERNAME')

    if not all([MONGODB_URI, MONGODB_USER, MONGODB_PASS, MONGODB_CLUSTERNAME]):
        raise ValueError("Missing one or more required MongoDB environment variables.")

    uri = f"mongodb+srv://{quote_plus(MONGODB_USER)}:{quote_plus(MONGODB_PASS)}@{MONGODB_URI}/?appName={MONGODB_CLUSTERNAME}"
    client = AsyncIOMotorClient(uri)
    logger.info("Created AsyncIOMotorClient")
    _client = client
    return _client


async def get_symbols_list():
    """Return all documents from the symbols collection."""
    client = get_mongo_client()
    db = client['EonTradingDB']
    return await db['symbols'].find({}).to_list(None)


getSymbolsList = get_symbols_list
