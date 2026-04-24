"""Replay mode — feed historical news through the live pipeline.

Usage:
  # Replay from MongoDB news collection
  PYTHONPATH=. python -m src.live.replay --start 2025-01-01 --end 2025-06-01

  # With specific broker/analyzer settings
  BROKER=log PYTHONPATH=. python -m src.live.replay --start 2025-04-01 --end 2025-04-30

This runs the exact same pipeline as live mode, but:
  - News comes from MongoDB (historical) instead of live sources
  - Clock is simulated to match each news event's timestamp
  - Prices are fetched at the simulated time via yfinance
  - Everything else (analyzer, trader, executor, broker) is identical
"""
import asyncio
import argparse
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()


async def main(start: str, end: str):
    from src.common.clock import clock
    from src.common.event_bus import LocalEventBus
    from src.common.events import CHANNEL_NEWS, NewsEvent
    from src.common.startup import banner
    from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer
    from src.live.analyzer_service import AnalyzerService
    from src.live.sentiment_trader import SentimentTrader
    from src.live.brokers.broker import TradeExecutor, LogBroker
    from src.common.position_store import PositionStore
    from src.data.utils.db_helper import get_mongo_client

    banner("EonTrading — Replay Mode", {
        "Period": f"{start} → {end}",
        "Analyzer": "LLM" if os.getenv("OPENAI_API_KEY") else "Keyword",
        "Broker": "LogBroker (dry run)",
        "Clock": "simulated (follows news timestamps)",
    })

    bus = LocalEventBus()
    await bus.start()

    analyzer = LLMSentimentAnalyzer() if os.getenv("OPENAI_API_KEY") else KeywordSentimentAnalyzer()
    broker = LogBroker()
    store = PositionStore()
    db = get_mongo_client()["EonTradingDB"]

    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15,
                             position_store=store,
                             trade_log=db["replay_trades"],
                             broker=broker)
    analyzer_svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    executor = TradeExecutor(bus, broker)

    await analyzer_svc.start()
    await trader.start()
    await executor.start()

    # Fetch historical news from MongoDB
    news_docs = list(db["news"].find({
        "timestamp": {"$gte": start, "$lte": end},
    }).sort("timestamp", 1))

    print(f"\n  📰 Replaying {len(news_docs)} news events from {start} to {end}\n")

    for i, doc in enumerate(news_docs):
        # Set simulated clock to news timestamp
        ts = doc.get("timestamp", "")
        if ts:
            try:
                clock.set_time(ts)
            except Exception:
                pass

        event = NewsEvent(
            source=doc.get("source", "replay"),
            headline=doc.get("headline", ""),
            timestamp=ts,
            url=doc.get("url", ""),
            body=doc.get("body", ""),
        )

        await bus.publish(CHANNEL_NEWS, event.to_dict())
        await asyncio.sleep(0.1)  # let the pipeline process

        if (i + 1) % 50 == 0:
            print(f"  ... {i + 1}/{len(news_docs)} events processed (clock: {clock.now().strftime('%Y-%m-%d %H:%M')})")

    await asyncio.sleep(0.5)  # let final fills settle
    clock.reset()

    # Summary
    print(f"\n{'═' * 50}")
    print(f"  Replay complete: {len(news_docs)} events")
    print(f"  Final holdings: {list(trader.holdings.keys()) or 'none'}")
    print(f"  Trades logged to: EonTradingDB.replay_trades")
    print(f"{'═' * 50}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay historical news through live pipeline")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()
    asyncio.run(main(args.start, args.end))
