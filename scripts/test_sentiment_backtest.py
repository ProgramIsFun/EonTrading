#!/usr/bin/env python3
"""Run sentiment backtest with synthetic news against real price data."""
from src.backtest.sentiment_backtest import run_sentiment_backtest

# Synthetic news events — real dates, fake headlines
AAPL_NEWS = [
    {"date": "2025-01-30", "headline": "Apple reports record earnings, profit surges past expectations"},
    {"date": "2025-03-10", "headline": "Apple stock rallies on strong iPhone demand and growth"},
    {"date": "2025-04-15", "headline": "Apple faces tariff ban on China imports, stock plunges"},
    {"date": "2025-05-01", "headline": "Apple beats earnings again, revenue growth accelerates"},
    {"date": "2025-06-10", "headline": "Apple announces major AI partnership, stock surges"},
    {"date": "2025-07-15", "headline": "Apple warns of weak demand, recession fears crash stock"},
    {"date": "2025-08-20", "headline": "Apple rebounds with record services revenue and profit"},
    {"date": "2025-10-01", "headline": "Apple iPhone 17 launch disappoints, stock drops on weak sales"},
    {"date": "2025-10-30", "headline": "Apple beats Q4 earnings, bullish outlook drives rally"},
    {"date": "2025-12-01", "headline": "Apple hit by EU investigation, stock declines sharply"},
]

TSLA_NEWS = [
    {"date": "2025-01-29", "headline": "Tesla earnings miss badly, stock crashes on weak deliveries"},
    {"date": "2025-03-05", "headline": "Tesla surges on record China sales and strong demand"},
    {"date": "2025-04-20", "headline": "Tesla faces tariff sanctions, stock plunges on trade war fears"},
    {"date": "2025-05-15", "headline": "Tesla beats delivery estimates, bullish analysts upgrade stock"},
    {"date": "2025-06-20", "headline": "Tesla recalls vehicles, safety investigation crashes stock"},
    {"date": "2025-07-25", "headline": "Tesla FSD approved in Europe, stock rallies on expansion"},
    {"date": "2025-09-10", "headline": "Tesla cuts prices again, bearish outlook on margin decline"},
    {"date": "2025-10-15", "headline": "Tesla robotaxi launch boosts stock, record optimism"},
    {"date": "2025-11-20", "headline": "Tesla layoffs announced, weak demand drops stock"},
    {"date": "2025-12-15", "headline": "Tesla ends year strong with record Q4 deliveries, stock surges"},
]

for symbol, news in [("AAPL", AAPL_NEWS), ("TSLA", TSLA_NEWS)]:
    print(f"\n{'='*60}")
    print(f"  Backtesting {symbol} with {len(news)} synthetic news events")
    print(f"{'='*60}")

    result = run_sentiment_backtest(
        symbol=symbol,
        news_events=news,
        start="2025-01-01",
        end="2025-12-31",
        initial_capital=10000.0,
        threshold=0.4,
        min_confidence=0.3,
    )

    print(result.summary())
    print(f"\n  Trade log:")
    for t in result.trades:
        pnl_str = f"  P&L: ${t.pnl:+,.2f}" if t.pnl != 0 else ""
        print(f"    {t.date}  {t.action:>12}  ${t.price:>8.2f}  sent:{t.sentiment:+.2f}  {t.headline[:50]}{pnl_str}")
