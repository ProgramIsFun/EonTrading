#!/usr/bin/env python3
"""Backfill historical news into MongoDB from any supported source.

Usage:
  python3 -m scripts.backfill_news --source finnhub --symbol AAPL --days 365
  python3 -m scripts.backfill_news --source newsapi --query "stock market" --days 30
"""
import argparse
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from src.common.clock import utcnow
from src.common.events import NewsEvent
from src.common.news_store import news_to_doc

load_dotenv()

from src.data.utils.db_helper import get_mongo_client

DB_NAME = "EonTradingDB"
COLLECTION = "news"


def get_collection():
    client = get_mongo_client()
    col = client[DB_NAME][COLLECTION]
    col.create_index("url", unique=True, sparse=True)
    return col


# --- Source: Finnhub ---

def backfill_finnhub(symbol: str, days: int, col):
    """Finnhub company news — free tier, ~1 year history per ticker."""
    import requests
    api_key = os.getenv("FINNHUB_KEY")
    if not api_key:
        print("Set FINNHUB_KEY env var. Get free key at https://finnhub.io/")
        return 0

    end = utcnow()
    start = end - timedelta(days=days)
    total = 0

    print(f"  Finnhub: {symbol} from {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
    try:
        resp = requests.get("https://finnhub.io/api/v1/company-news", params={
            "token": api_key,
            "symbol": symbol,
            "from": start.strftime("%Y-%m-%d"),
            "to": end.strftime("%Y-%m-%d"),
        }, timeout=15)
        articles = resp.json()
        for a in articles:
            url = a.get("url", "")
            if url and col.find_one({"url": url}):
                continue
            event = NewsEvent(
                source="finnhub", headline=a.get("headline", ""),
                timestamp=datetime.utcfromtimestamp(a.get("datetime", 0)).isoformat() + "Z",
                url=url, body=a.get("summary", ""),
            )
            doc = news_to_doc(event, origin="backfill")
            doc["symbol"] = symbol
            col.insert_one(doc)
            total += 1
        print(f"  → {total} new articles (skipped {len(articles) - total} dupes)")
    except Exception as e:
        print(f"  Finnhub error: {e}")
    return total


# --- Source: NewsAPI ---

def backfill_newsapi(query: str, days: int, col):
    """NewsAPI everything endpoint — free tier: 1 month, 100 req/day."""
    import requests
    api_key = os.getenv("NEWSAPI_KEY")
    if not api_key:
        print("Set NEWSAPI_KEY env var. Get free key at https://newsapi.org/")
        return 0

    end = utcnow()
    start = end - timedelta(days=min(days, 30))  # free tier max 30 days
    total = 0

    print(f"  NewsAPI: '{query}' from {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
    try:
        resp = requests.get("https://newsapi.org/v2/everything", params={
            "apiKey": api_key,
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 100,
            "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }, timeout=15)
        articles = resp.json().get("articles", [])
        for a in articles:
            url = a.get("url", "")
            if url and col.find_one({"url": url}):
                continue
            event = NewsEvent(
                source="newsapi", headline=a.get("title", ""),
                timestamp=a.get("publishedAt", ""),
                url=url, body=a.get("description", ""),
            )
            col.insert_one(news_to_doc(event, origin="backfill"))
            total += 1
        print(f"  → {total} new articles (skipped {len(articles) - total} dupes)")
    except Exception as e:
        print(f"  NewsAPI error: {e}")
    return total


# --- Registry ---

SOURCES = {
    "finnhub": {"fn": backfill_finnhub, "args": ["symbol", "days"]},
    "newsapi": {"fn": backfill_newsapi, "args": ["query", "days"]},
    # Add new sources here:
    # "your_source": {"fn": backfill_your_source, "args": ["symbol", "days"]},
}


def main():
    parser = argparse.ArgumentParser(description="Backfill historical news to MongoDB")
    parser.add_argument("--source", required=True, choices=SOURCES.keys(), help="News source")
    parser.add_argument("--symbol", default="AAPL", help="Stock symbol (for finnhub)")
    parser.add_argument("--query", default="stock market OR earnings OR tariff", help="Search query (for newsapi)")
    parser.add_argument("--days", type=int, default=30, help="Days of history to fetch")
    args = parser.parse_args()

    col = get_collection()
    src = SOURCES[args.source]

    print(f"Backfilling from {args.source} into {DB_NAME}.{COLLECTION}")
    kwargs = {}
    if "symbol" in src["args"]:
        kwargs["symbol"] = args.symbol
    if "query" in src["args"]:
        kwargs["query"] = args.query
    kwargs["days"] = args.days
    kwargs["col"] = col

    src["fn"](**kwargs)
    print(f"\nDone. Total in DB: {col.count_documents({})}")


if __name__ == "__main__":
    main()
