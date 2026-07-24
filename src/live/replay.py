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
import argparse
import asyncio

async def main(start: str, end: str):
    from src.common.clock import clock
    from src.common.event_bus import LocalEventBus
    from src.common.events import CHANNEL_NEWS, NewsEvent
    from src.common.position_store import InMemoryPositionStore
    from src.common.startup import banner
    from src.common.trading_logic import TradingLogic
    from src.data.utils.db_helper import get_mongo_client
    from src.live.analyzer_service import AnalyzerService
    from src.live.brokers.broker import PaperBroker, TradeExecutor
    from src.live.order_logger import mongo_log_order
    from src.live.price_monitor import PriceMonitor
    from src.live.sentiment_trader import SentimentTrader
    from src.settings import settings
    from src.strategies.sentiment import KeywordSentimentAnalyzer, LLMSentimentAnalyzer

    banner("EonTrading — Replay Mode", {
        "Period": f"{start} → {end}",
        "Analyzer": "LLM" if settings.openai_api_key else "Keyword",
        "Broker": "PaperBroker (dry run)",
        "Clock": "simulated (follows news timestamps)",
    })

    bus = LocalEventBus()
    await bus.start()

    analyzer = LLMSentimentAnalyzer() if (settings.openai_api_key or settings.opencode_api_key) else KeywordSentimentAnalyzer()
    broker = PaperBroker()
    store = InMemoryPositionStore()
    logic = TradingLogic(threshold=0.4, min_confidence=0.15)
    db = get_mongo_client()["EonTradingDB"]
    price_monitor = PriceMonitor(bus, store, logic)

    trader = SentimentTrader(bus, logic=logic, position_store=store, broker=broker)
    analyzer_svc = AnalyzerService(bus, analyzer=analyzer, get_positions=store.get_positions)
    executor = TradeExecutor(bus, broker, log_order=mongo_log_order)

    await analyzer_svc.start()
    await trader.start()
    await executor.start()

    # Fetch historical news from MongoDB
    news_docs = list(db["news"].find({
        "timestamp": {"$gte": start, "$lte": end},
    }).sort("timestamp", 1))

    # Group news by date for daily interleaving
    from datetime import datetime, timedelta
    news_by_date: dict[str, list] = {}
    for doc in news_docs:
        day = doc.get("timestamp", "")[:10]
        if day:
            news_by_date.setdefault(day, []).append(doc)

    print(f"\n  📰 Replaying {len(news_docs)} news events from {start} to {end}\n")

    start_dt = datetime.strptime(start, "%Y-%m-%d")
    end_dt = datetime.strptime(end, "%Y-%m-%d")
    current = start_dt
    event_count = 0
    day_count = 0

    while current <= end_dt:
        if current.weekday() >= 5:  # skip weekends
            current += timedelta(days=1)
            continue

        day_str = current.strftime("%Y-%m-%d")
        close_ts = f"{day_str}T16:00:00Z"
        day_count += 1

        # Process any news events on this day (at their actual timestamp)
        for doc in news_by_date.get(day_str, []):
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
            await asyncio.sleep(0.05)
            event_count += 1

        # Check SL/TP at market close every trading day
        try:
            clock.set_time(close_ts)
        except Exception:
            pass
        if price_monitor:
            await price_monitor.check_once(as_of=close_ts)

        if day_count % 20 == 0:
            pct = (current - start_dt).total_seconds() / max((end_dt - start_dt).total_seconds(), 1) * 100
            print(f"  ... day {day_count} ({pct:.0f}%) — {(current - start_dt).days}d elapsed, {event_count} news events")

        current += timedelta(days=1)

    await asyncio.sleep(0.5)  # let final fills settle
    clock.reset()

    # Summary
    holdings = store.get_positions() if store else {}
    print(f"\n{'═' * 50}")
    print(f"  Replay complete — {day_count} trading days, {event_count} news events")
    print(f"  Final holdings: {list(holdings.keys()) or 'none'}")
    print("  Trades logged to: EonTradingDB.replay_trades")
    print(f"{'═' * 50}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Replay historical news through live pipeline")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()
    asyncio.run(main(args.start, args.end))
