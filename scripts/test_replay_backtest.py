#!/usr/bin/env python3
"""Backtest by replaying pre-scored sentiment events through the live pipeline.

Skips the Analyzer — you provide the scores directly.
Tests: SentimentTrader + TradingLogic with known real events.
"""
import asyncio
from src.common.event_bus import LocalEventBus
from src.common.events import CHANNEL_SENTIMENT, CHANNEL_TRADE, TradeEvent
from src.live.sentiment_trader import SentimentTrader
from src.live.brokers.broker import TradeExecutor, LogBroker

# Pre-scored real events — as if the Analyzer already ran
# These are what a good LLM analyzer SHOULD output for major 2025 events
EVENTS = [
    # Jan 2025
    {"symbols": ["NVDA"], "sentiment": 0.8, "confidence": 0.9, "headline": "Nvidia unveils Blackwell GPU at CES"},
    {"symbols": ["NVDA"], "sentiment": -0.9, "confidence": 0.95, "headline": "DeepSeek AI shocks market, Nvidia crashes on cheaper AI fears"},
    {"symbols": ["TSLA"], "sentiment": -0.7, "confidence": 0.8, "headline": "Tesla Q4 earnings miss, revenue falls short"},
    {"symbols": ["META"], "sentiment": 0.8, "confidence": 0.9, "headline": "Meta Q4 earnings beat, ad revenue growth accelerates"},
    {"symbols": ["AAPL"], "sentiment": 0.7, "confidence": 0.85, "headline": "Apple reports record Q1 revenue $124B"},

    # Feb 2025
    {"symbols": ["GOOGL"], "sentiment": -0.6, "confidence": 0.8, "headline": "Alphabet Q4 earnings miss on cloud revenue"},
    {"symbols": ["AMZN"], "sentiment": 0.7, "confidence": 0.85, "headline": "Amazon Q4 earnings beat, AWS growth accelerates"},
    {"symbols": ["META"], "sentiment": -0.7, "confidence": 0.85, "headline": "Meta announces $65B AI spending, stock drops on cost fears"},
    {"symbols": ["NVDA"], "sentiment": 0.9, "confidence": 0.95, "headline": "Nvidia Q4 earnings smash records, data center +93%"},

    # Mar 2025
    {"symbols": ["TSLA"], "sentiment": -0.8, "confidence": 0.9, "headline": "Tesla sales crash in Europe, down 45% on Musk backlash"},
    {"symbols": ["GOOGL"], "sentiment": 0.6, "confidence": 0.7, "headline": "Google acquires Wiz for $32B"},
    {"symbols": ["TSLA"], "sentiment": 0.6, "confidence": 0.7, "headline": "Musk promises affordable Tesla under $30K"},

    # Apr 2025 — tariff chaos
    {"symbols": ["AAPL", "NVDA", "AMZN", "META", "MSFT", "GOOGL"], "sentiment": -0.9, "confidence": 0.95, "headline": "Trump announces sweeping tariffs on China"},
    {"symbols": ["AAPL", "NVDA", "AMZN"], "sentiment": 0.7, "confidence": 0.8, "headline": "Trump pauses tariffs 90 days, relief rally"},
    {"symbols": ["TSLA"], "sentiment": -0.8, "confidence": 0.9, "headline": "Tesla Q1 earnings plunge 71%"},
    {"symbols": ["TSLA"], "sentiment": 0.8, "confidence": 0.85, "headline": "Musk to reduce DOGE role, focus on Tesla"},
    {"symbols": ["GOOGL"], "sentiment": 0.7, "confidence": 0.85, "headline": "Alphabet Q1 earnings beat, cloud surges"},
    {"symbols": ["META"], "sentiment": 0.8, "confidence": 0.9, "headline": "Meta Q1 earnings crush expectations, revenue +16%"},
    {"symbols": ["MSFT"], "sentiment": 0.8, "confidence": 0.9, "headline": "Microsoft Q3 earnings crush, Azure reaccelerates to 35%"},

    # May 2025
    {"symbols": ["AAPL"], "sentiment": 0.7, "confidence": 0.8, "headline": "Apple Q2 earnings beat, services revenue record"},
    {"symbols": ["AMZN"], "sentiment": -0.5, "confidence": 0.7, "headline": "Amazon Q1 beats but weak Q2 guidance drops stock"},
]


async def main():
    bus = LocalEventBus()
    await bus.start()

    # Collect trades
    executed_trades: list[dict] = []

    async def capture_trade(msg):
        trade = TradeEvent.from_dict(msg)
        executed_trades.append(msg)
        action_icon = "🟢" if trade.action == "buy" else "🔴"
        print(f"  {action_icon} {trade.action.upper():>4} {trade.symbol:<6} | {trade.reason}")

    await bus.subscribe(CHANNEL_TRADE, capture_trade)

    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15)
    await trader.start()

    print("=" * 70)
    print("  Replay backtest — pre-scored events through live pipeline")
    print("=" * 70)

    for ev in EVENTS:
        sentiment_msg = {
            "source": "backtest",
            "headline": ev["headline"],
            "timestamp": "2025-01-01T00:00:00Z",
            "analyzed_at": "2025-01-01T00:00:00Z",
            "symbols": ev["symbols"],
            "sector": "",
            "sentiment": ev["sentiment"],
            "confidence": ev["confidence"],
            "urgency": "normal",
        }
        await bus.publish(CHANNEL_SENTIMENT, sentiment_msg)
        await asyncio.sleep(0.05)  # let async tasks process

    print(f"\n{'─' * 70}")
    print(f"  Total trades: {len(executed_trades)}")
    print(f"  Final holdings: {dict(trader.holdings)}")

    buys = sum(1 for t in executed_trades if t["action"] == "buy")
    sells = sum(1 for t in executed_trades if t["action"] == "sell")
    print(f"  Buys: {buys}, Sells: {sells}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    asyncio.run(main())
