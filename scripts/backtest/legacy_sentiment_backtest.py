#!/usr/bin/env python3
"""Run sentiment backtest with synthetic news against real price data."""
from src.backtest.sentiment_backtest import run_sentiment_backtest

# Synthetic news with timestamps (news hits mid-day)
AAPL_NEWS = [
    {"date": "2025-01-30T14:30:00", "headline": "Apple reports record earnings, profit surges past expectations"},
    {"date": "2025-03-10T15:00:00", "headline": "Apple stock rallies on strong iPhone demand and growth"},
    {"date": "2025-04-15T16:00:00", "headline": "Apple faces tariff ban on China imports, stock plunges"},
    {"date": "2025-05-01T14:00:00", "headline": "Apple beats earnings again, revenue growth accelerates"},
    {"date": "2025-06-10T15:30:00", "headline": "Apple announces major AI partnership, stock surges"},
    {"date": "2025-07-15T14:30:00", "headline": "Apple warns of weak demand, recession fears crash stock"},
    {"date": "2025-08-20T16:00:00", "headline": "Apple rebounds with record services revenue and profit"},
    {"date": "2025-10-01T15:00:00", "headline": "Apple iPhone 17 launch disappoints, stock drops on weak sales"},
    {"date": "2025-10-30T14:00:00", "headline": "Apple beats Q4 earnings, bullish outlook drives rally"},
    {"date": "2025-12-01T15:30:00", "headline": "Apple hit by EU investigation, stock declines sharply"},
]

TSLA_NEWS = [
    {"date": "2025-01-29T16:00:00", "headline": "Tesla earnings miss badly, stock crashes on weak deliveries"},
    {"date": "2025-03-05T14:30:00", "headline": "Tesla surges on record China sales and strong demand"},
    {"date": "2025-04-21T15:00:00", "headline": "Tesla faces tariff sanctions, stock plunges on trade war fears"},
    {"date": "2025-05-15T14:00:00", "headline": "Tesla beats delivery estimates, bullish analysts upgrade stock"},
    {"date": "2025-06-20T15:30:00", "headline": "Tesla recalls vehicles, safety investigation crashes stock"},
    {"date": "2025-07-25T14:30:00", "headline": "Tesla FSD approved in Europe, stock rallies on expansion"},
    {"date": "2025-09-10T16:00:00", "headline": "Tesla cuts prices again, bearish outlook on margin decline"},
    {"date": "2025-10-15T15:00:00", "headline": "Tesla robotaxi launch boosts stock, record optimism"},
    {"date": "2025-11-20T14:00:00", "headline": "Tesla layoffs announced, weak demand drops stock"},
    {"date": "2025-12-15T15:30:00", "headline": "Tesla ends year strong with record Q4 deliveries, stock surges"},
]

for symbol, news in [("AAPL", AAPL_NEWS), ("TSLA", TSLA_NEWS)]:
    print(f"\n{'='*70}")
    print(f"  {symbol} — Hourly vs Daily comparison (Full config: scaled + SL/TP)")
    print(f"{'='*70}")
    print(f"  {'Interval':<12s} {'Return':>8s} {'MaxDD':>7s} {'Trades':>7s} {'WinR':>6s} {'Final':>10s}")
    print(f"  {'─'*12} {'─'*8} {'─'*7} {'─'*7} {'─'*6} {'─'*10}")

    for iv in ["1h", "1d"]:
        result = run_sentiment_backtest(
            symbol=symbol, news_events=news,
            start="2025-01-01", end="2025-12-31",
            initial_capital=10000.0, threshold=0.4, min_confidence=0.3,
            scale_by_sentiment=True, max_hold_days=30,
            stop_loss_pct=0.05, take_profit_pct=0.10,
            interval=iv,
        )
        print(f"  {iv:<12s} {result.total_return_pct:>+7.2f}% {result.max_drawdown_pct:>6.2f}% {result.total_trades:>7} {result.win_rate:>5.1f}% ${result.final_value:>9,.2f}")

    # Show hourly trade log
    print("\n  Hourly trade log:")
    result = run_sentiment_backtest(
        symbol=symbol, news_events=news,
        start="2025-01-01", end="2025-12-31",
        initial_capital=10000.0, threshold=0.4, min_confidence=0.3,
        scale_by_sentiment=True, max_hold_days=30,
        stop_loss_pct=0.05, take_profit_pct=0.10,
        interval="1h",
    )
    for t in result.trades:
        pnl_str = f"  P&L: ${t.pnl:+,.2f}" if t.pnl != 0 else ""
        print(f"    {t.date}  {t.action:>14}  {t.shares:>4}sh  ${t.price:>8.2f}  sent:{t.sentiment:+.2f}  {t.headline[:35]}{pnl_str}")
