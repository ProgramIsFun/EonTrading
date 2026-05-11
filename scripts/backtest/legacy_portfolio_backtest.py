#!/usr/bin/env python3
"""Portfolio backtest — single news feed, shared capital, multi-symbol."""
from src.backtest.portfolio_backtest import run_portfolio_backtest
from src.common.costs import US_STOCKS

# All news in one chronological pool
ALL_NEWS = [
    {"date": "2025-01-06T10:00:00", "headline": "Nvidia unveils new Blackwell GPU chips at CES, stock rallies"},
    {"date": "2025-01-27T09:30:00", "headline": "DeepSeek AI model shocks market, Nvidia stock crashes on cheaper AI fears"},
    {"date": "2025-01-29T16:30:00", "headline": "Tesla Q4 earnings miss estimates, revenue falls short of expectations"},
    {"date": "2025-01-29T16:30:00", "headline": "Meta Q4 earnings beat estimates, ad revenue growth accelerates"},
    {"date": "2025-01-29T16:30:00", "headline": "Microsoft Q2 earnings beat estimates but Azure growth slows, stock drops"},
    {"date": "2025-01-30T16:30:00", "headline": "Apple reports record Q1 revenue of $124B, beating estimates"},
    {"date": "2025-01-31T10:00:00", "headline": "Meta launches Llama 4 AI model, stock rallies on AI leadership"},
    {"date": "2025-02-04T16:30:00", "headline": "Alphabet Q4 earnings miss on cloud revenue, Google stock drops"},
    {"date": "2025-02-06T16:30:00", "headline": "Amazon Q4 earnings beat estimates, AWS revenue growth accelerates"},
    {"date": "2025-02-10T10:00:00", "headline": "Tesla sales plunge in China, BYD overtakes Tesla in global EV sales"},
    {"date": "2025-02-14T10:00:00", "headline": "Meta announces massive AI spending increase to $65B, stock drops on cost fears"},
    {"date": "2025-02-26T16:30:00", "headline": "Nvidia Q4 earnings smash records, data center revenue surges 93%"},
    {"date": "2025-03-03T14:00:00", "headline": "Tesla sales crash in Europe, down 45% amid Musk backlash and boycotts"},
    {"date": "2025-03-12T10:00:00", "headline": "Google acquires cloud security firm Wiz for $32B, biggest deal ever"},
    {"date": "2025-03-24T10:00:00", "headline": "Tesla stock rallies as Musk promises new affordable model under $30K"},
    {"date": "2025-03-26T09:30:00", "headline": "Apple loses antitrust case, judge rules App Store violates court order"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump announces sweeping tariffs on China, Apple supply chain at risk"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs threaten chip exports to China, Nvidia drops sharply"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs threaten Amazon e-commerce costs, stock drops sharply"},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs for 90 days, Apple stock surges on relief rally"},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs 90 days, Nvidia rallies on trade relief"},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs 90 days, Amazon surges on trade relief"},
    {"date": "2025-04-15T09:30:00", "headline": "Nvidia announces $500B US AI infrastructure investment plan"},
    {"date": "2025-04-22T16:30:00", "headline": "Tesla Q1 earnings plunge 71%, worst quarter in years"},
    {"date": "2025-04-23T10:00:00", "headline": "Elon Musk says he will reduce DOGE role to focus on Tesla, stock surges"},
    {"date": "2025-04-24T16:30:00", "headline": "Alphabet Q1 earnings beat estimates, cloud revenue surges, stock rallies"},
    {"date": "2025-04-30T16:30:00", "headline": "Meta Q1 earnings crush expectations, revenue up 16% on strong ad demand"},
    {"date": "2025-04-30T16:30:00", "headline": "Microsoft Q3 earnings crush estimates, Azure growth reaccelerates to 35%"},
    {"date": "2025-05-01T16:30:00", "headline": "Apple Q2 earnings beat expectations, services revenue hits record"},
    {"date": "2025-05-01T16:30:00", "headline": "Amazon Q1 earnings beat, but weak Q2 guidance drops stock"},
    {"date": "2025-06-09T13:00:00", "headline": "Apple announces Apple Intelligence AI features at WWDC 2025"},
]

print("\n" + "=" * 70)
print("  PORTFOLIO BACKTEST — shared $70K capital, multi-symbol")
print("=" * 70)

result = run_portfolio_backtest(
    news_events=ALL_NEWS,
    start="2025-01-01", end="2025-12-31",
    initial_capital=70000.0,
    threshold=0.4, min_confidence=0.15,
    cost_model=US_STOCKS,
    max_allocation=0.2,  # max 20% per position
    stop_loss_pct=0.05, take_profit_pct=0.10,
    max_hold_days=30, cooldown_days=1,
)

print(f"\n{result.summary()}")
print("\n  Trade log:")
print(f"  {'Date':<22s} {'Symbol':<7s} {'Action':<14s} {'Shares':>6s} {'Price':>9s} {'Sent':>6s} {'P&L':>10s}  Headline")
print(f"  {'─'*22} {'─'*7} {'─'*14} {'─'*6} {'─'*9} {'─'*6} {'─'*10}  {'─'*40}")
for t in result.trades:
    pnl_str = f"${t.pnl:+,.2f}" if t.pnl != 0 else ""
    print(f"  {t.date:<22s} {t.symbol:<7s} {t.action:<14s} {t.shares:>6} ${t.price:>8.2f} {t.sentiment:>+5.2f} {pnl_str:>10s}  {t.headline[:40]}")

print(f"\n{'='*70}\n")
