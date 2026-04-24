import os
import logging
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

    uri = f"mongodb+srv://{MONGODB_USER}:{MONGODB_PASS}@{MONGODB_URI}/?appName={MONGODB_CLUSTERNAME}"

    # Create a new client
    client = MongoClient(uri, server_api=ServerApi('1'))

    # Send a ping to confirm a successful connection
    try:
        client.admin.command('ping')
        logger.info("Successfully connected to MongoDB")
        _client = client
        return _client
    except Exception as e:
        logger.error("Failed to connect to MongoDB: %s", e)
        return None
    

def getSymbolsList():
    # get list of stock first
    client = get_mongo_client()
    db = client['EonTradingDB']
    collection = db['symbols']
    documents = collection.find({})
    stock_list = []
    for doc in documents:
        stock_list.append(doc)
    return stock_list