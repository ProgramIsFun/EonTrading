#!/usr/bin/env python3
"""Replay backtest with P&L — pre-scored events through live pipeline + real prices."""
import asyncio
from datetime import datetime

import yfinance as yf

from src.common.costs import US_STOCKS
from src.common.event_bus import LocalEventBus
from src.common.events import CHANNEL_SENTIMENT, CHANNEL_TRADE, TradeEvent
from src.live.sentiment_trader import SentimentTrader

# Pre-scored real events with timestamps
EVENTS = [
    {"date": "2025-01-06", "symbols": ["NVDA"], "sentiment": 0.8, "confidence": 0.9, "headline": "Nvidia unveils Blackwell GPU at CES"},
    {"date": "2025-01-27", "symbols": ["NVDA"], "sentiment": -0.9, "confidence": 0.95, "headline": "DeepSeek AI shocks market, Nvidia crashes"},
    {"date": "2025-01-29", "symbols": ["META"], "sentiment": 0.8, "confidence": 0.9, "headline": "Meta Q4 earnings beat, ad revenue growth accelerates"},
    {"date": "2025-01-30", "symbols": ["AAPL"], "sentiment": 0.7, "confidence": 0.85, "headline": "Apple reports record Q1 revenue $124B"},
    {"date": "2025-02-04", "symbols": ["GOOGL"], "sentiment": -0.6, "confidence": 0.8, "headline": "Alphabet Q4 earnings miss on cloud revenue"},
    {"date": "2025-02-06", "symbols": ["AMZN"], "sentiment": 0.7, "confidence": 0.85, "headline": "Amazon Q4 earnings beat, AWS growth accelerates"},
    {"date": "2025-02-14", "symbols": ["META"], "sentiment": -0.7, "confidence": 0.85, "headline": "Meta $65B AI spending, stock drops on cost fears"},
    {"date": "2025-02-26", "symbols": ["NVDA"], "sentiment": 0.9, "confidence": 0.95, "headline": "Nvidia Q4 earnings smash records, data center +93%"},
    {"date": "2025-03-03", "symbols": ["TSLA"], "sentiment": -0.8, "confidence": 0.9, "headline": "Tesla sales crash in Europe, down 45%"},
    {"date": "2025-03-12", "symbols": ["GOOGL"], "sentiment": 0.6, "confidence": 0.7, "headline": "Google acquires Wiz for $32B"},
    {"date": "2025-03-24", "symbols": ["TSLA"], "sentiment": 0.6, "confidence": 0.7, "headline": "Musk promises affordable Tesla under $30K"},
    {"date": "2025-04-03", "symbols": ["AAPL", "NVDA", "AMZN", "META", "MSFT", "GOOGL"], "sentiment": -0.9, "confidence": 0.95, "headline": "Trump sweeping tariffs on China"},
    {"date": "2025-04-09", "symbols": ["AAPL", "NVDA", "AMZN"], "sentiment": 0.7, "confidence": 0.8, "headline": "Trump pauses tariffs 90 days"},
    {"date": "2025-04-22", "symbols": ["TSLA"], "sentiment": -0.8, "confidence": 0.9, "headline": "Tesla Q1 earnings plunge 71%"},
    {"date": "2025-04-23", "symbols": ["TSLA"], "sentiment": 0.8, "confidence": 0.85, "headline": "Musk to reduce DOGE role, focus on Tesla"},
    {"date": "2025-04-24", "symbols": ["GOOGL"], "sentiment": 0.7, "confidence": 0.85, "headline": "Alphabet Q1 earnings beat, cloud surges"},
    {"date": "2025-04-30", "symbols": ["META"], "sentiment": 0.8, "confidence": 0.9, "headline": "Meta Q1 earnings crush, revenue +16%"},
    {"date": "2025-04-30", "symbols": ["MSFT"], "sentiment": 0.8, "confidence": 0.9, "headline": "Microsoft Q3 crush, Azure 35%"},
    {"date": "2025-05-01", "symbols": ["AAPL"], "sentiment": 0.7, "confidence": 0.8, "headline": "Apple Q2 earnings beat, services record"},
    {"date": "2025-05-01", "symbols": ["AMZN"], "sentiment": -0.5, "confidence": 0.7, "headline": "Amazon weak Q2 guidance drops stock"},
]


def fetch_close_price(symbol, date_str):
    """Get close price on a given date."""
    try:
        df = yf.download(symbol, start=date_str, period="5d", auto_adjust=True, progress=False)
        if not df.empty:
            return float(df["Close"].iloc[0]) if "Close" in df.columns else float(df.iloc[0, 0])
    except Exception:
        pass
    return None


async def main():
    bus = LocalEventBus()
    await bus.start()

    trades_log = []

    async def capture_trade(msg):
        trades_log.append(msg)

    await bus.subscribe(CHANNEL_TRADE, capture_trade)

    trader = SentimentTrader(bus, threshold=0.4, min_confidence=0.15)
    await trader.start()

    print("=" * 75)
    print("  Replay backtest with P&L — pre-scored events + real prices")
    print("=" * 75)

    # Replay events
    for ev in EVENTS:
        sentiment_msg = {
            "source": "backtest", "headline": ev["headline"],
            "timestamp": ev["date"] + "T14:00:00Z",
            "analyzed_at": ev["date"] + "T14:00:00Z",
            "symbols": ev["symbols"], "sector": "",
            "sentiment": ev["sentiment"], "confidence": ev["confidence"],
            "urgency": "normal",
        }
        await bus.publish(CHANNEL_SENTIMENT, sentiment_msg)
        await asyncio.sleep(0.05)

    # Now calculate P&L using real prices
    print(f"\n  Fetching prices for {len(trades_log)} trades...")
    positions = {}  # symbol → {shares_concept, entry_price}
    total_pnl = 0
    capital = 70000
    cash = capital
    allocation = 0.2  # 20% per trade

    print(f"\n  {'Date':<12} {'Action':>5} {'Symbol':<7} {'Price':>9} {'P&L':>10}  Headline")
    print(f"  {'─'*12} {'─'*5} {'─'*7} {'─'*9} {'─'*10}  {'─'*40}")

    for t in trades_log:
        symbol = t["symbol"]
        action = t["action"]
        date = EVENTS[[i for i, e in enumerate(EVENTS) if symbol in e["symbols"] and
                       ((e["sentiment"] >= 0.4 and action == "buy") or (e["sentiment"] <= -0.4 and action == "sell"))][0]]["date"] if True else ""

        # Find the matching event date
        for ev in EVENTS:
            if symbol in ev["symbols"]:
                if (action == "buy" and ev["sentiment"] >= 0.4) or (action == "sell" and ev["sentiment"] <= -0.4):
                    date = ev["date"]

        price = fetch_close_price(symbol, date)
        if price is None:
            continue

        pnl_str = ""
        if action == "buy" and symbol not in positions:
            shares = int((cash * allocation) / price)
            if shares > 0:
                cost = US_STOCKS.buy_cost(price, shares)
                cash -= shares * price + cost
                positions[symbol] = {"shares": shares, "entry": price}
        elif action == "sell" and symbol in positions:
            pos = positions.pop(symbol)
            cost = US_STOCKS.sell_cost(price, pos["shares"])
            pnl = (price - pos["entry"]) * pos["shares"] - cost
            cash += pos["shares"] * price - cost
            total_pnl += pnl
            pnl_str = f"${pnl:+,.2f}"

        print(f"  {date:<12} {action:>5} {symbol:<7} ${price:>8.2f} {pnl_str:>10}  {t.get('reason', '')[:40]}")

    # Value remaining positions
    unrealized = 0
    for sym, pos in positions.items():
        current = fetch_close_price(sym, "2025-06-01")
        if current:
            unrealized += (current - pos["entry"]) * pos["shares"]

    final = cash + sum(pos["shares"] * (fetch_close_price(sym, "2025-06-01") or pos["entry"]) for sym, pos in positions.items())

    print(f"\n  {'─'*75}")
    print(f"  Initial capital:  ${capital:>10,.2f}")
    print(f"  Realized P&L:     ${total_pnl:>+10,.2f}")
    print(f"  Unrealized P&L:   ${unrealized:>+10,.2f}")
    print(f"  Final value:      ${final:>10,.2f}")
    print(f"  Total return:     {(final - capital) / capital * 100:>+.2f}%")
    print(f"  Still holding:    {list(positions.keys())}")
    print(f"{'='*75}\n")


if __name__ == "__main__":
    asyncio.run(main())
