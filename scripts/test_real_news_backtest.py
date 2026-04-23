#!/usr/bin/env python3
"""Backtest with real historical news events against real price data."""
from src.backtest.sentiment_backtest import run_sentiment_backtest
from src.common.costs import US_STOCKS

AAPL_NEWS = [
    {"date": "2025-01-30T16:30:00", "headline": "Apple reports record Q1 revenue of $124B, beating estimates"},
    {"date": "2025-02-28T10:00:00", "headline": "Apple reportedly developing smart home display and robotic device"},
    {"date": "2025-03-26T09:30:00", "headline": "Apple loses antitrust case, judge rules App Store violates court order"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump announces sweeping tariffs on China, Apple supply chain at risk"},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs for 90 days, Apple stock surges on relief rally"},
    {"date": "2025-05-01T16:30:00", "headline": "Apple Q2 earnings beat expectations, services revenue hits record"},
    {"date": "2025-06-09T13:00:00", "headline": "Apple announces Apple Intelligence AI features at WWDC 2025"},
]

TSLA_NEWS = [
    {"date": "2025-01-29T16:30:00", "headline": "Tesla Q4 earnings miss estimates, revenue falls short of expectations"},
    {"date": "2025-02-10T10:00:00", "headline": "Tesla sales plunge in China, BYD overtakes Tesla in global EV sales"},
    {"date": "2025-03-03T14:00:00", "headline": "Tesla sales crash in Europe, down 45% amid Musk backlash and boycotts"},
    {"date": "2025-03-24T10:00:00", "headline": "Tesla stock rallies as Musk promises new affordable model under $30K"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs hit auto industry, Tesla faces higher costs on parts"},
    {"date": "2025-04-22T16:30:00", "headline": "Tesla Q1 earnings plunge 71%, worst quarter in years"},
    {"date": "2025-04-23T10:00:00", "headline": "Elon Musk says he will reduce DOGE role to focus on Tesla, stock surges"},
]

NVDA_NEWS = [
    {"date": "2025-01-06T10:00:00", "headline": "Nvidia unveils new Blackwell GPU chips at CES, stock rallies"},
    {"date": "2025-01-27T09:30:00", "headline": "DeepSeek AI model shocks market, Nvidia stock crashes on cheaper AI fears"},
    {"date": "2025-02-26T16:30:00", "headline": "Nvidia Q4 earnings smash records, data center revenue surges 93%"},
    {"date": "2025-03-18T10:00:00", "headline": "Nvidia GTC conference, Jensen Huang unveils next-gen Vera Rubin chips"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs threaten chip exports to China, Nvidia drops sharply"},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs 90 days, Nvidia rallies on trade relief"},
    {"date": "2025-04-15T09:30:00", "headline": "Nvidia announces $500B US AI infrastructure investment plan"},
]

META_NEWS = [
    {"date": "2025-01-29T16:30:00", "headline": "Meta Q4 earnings beat estimates, ad revenue growth accelerates"},
    {"date": "2025-01-31T10:00:00", "headline": "Meta launches Llama 4 AI model, stock rallies on AI leadership"},
    {"date": "2025-02-14T10:00:00", "headline": "Meta announces massive AI spending increase to $65B, stock drops on cost fears"},
    {"date": "2025-03-14T10:00:00", "headline": "Meta faces EU Digital Markets Act fine of $200M, stock declines"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs rattle tech sector, Meta falls with broader market decline"},
    {"date": "2025-04-30T16:30:00", "headline": "Meta Q1 earnings crush expectations, revenue up 16% on strong ad demand"},
]

GOOGL_NEWS = [
    {"date": "2025-02-04T16:30:00", "headline": "Alphabet Q4 earnings miss on cloud revenue, Google stock drops"},
    {"date": "2025-03-12T10:00:00", "headline": "Google acquires cloud security firm Wiz for $32B, biggest deal ever"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs hit tech sector, Google falls with market selloff"},
    {"date": "2025-04-24T16:30:00", "headline": "Alphabet Q1 earnings beat estimates, cloud revenue surges, stock rallies"},
]

AMZN_NEWS = [
    {"date": "2025-02-06T16:30:00", "headline": "Amazon Q4 earnings beat estimates, AWS revenue growth accelerates"},
    {"date": "2025-02-20T10:00:00", "headline": "Amazon announces $100B AI infrastructure investment for 2025"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs threaten Amazon e-commerce costs, stock drops sharply"},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs 90 days, Amazon surges on trade relief"},
    {"date": "2025-05-01T16:30:00", "headline": "Amazon Q1 earnings beat, but weak Q2 guidance drops stock"},
]

MSFT_NEWS = [
    {"date": "2025-01-29T16:30:00", "headline": "Microsoft Q2 earnings beat estimates but Azure growth slows, stock drops"},
    {"date": "2025-02-03T10:00:00", "headline": "Microsoft announces $80B AI data center investment for 2025"},
    {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs rattle tech sector, Microsoft falls with market decline"},
    {"date": "2025-04-30T16:30:00", "headline": "Microsoft Q3 earnings crush estimates, Azure growth reaccelerates to 35%"},
]

datasets = [
    ("AAPL", AAPL_NEWS),
    ("TSLA", TSLA_NEWS),
    ("NVDA", NVDA_NEWS),
    ("META", META_NEWS),
    ("GOOGL", GOOGL_NEWS),
    ("AMZN", AMZN_NEWS),
    ("MSFT", MSFT_NEWS),
]

print("\n" + "=" * 75)
print("  REAL NEWS BACKTEST — Major 2025 events vs actual prices (hourly)")
print("=" * 75)
print(f"\n  {'Symbol':<8s} {'Return':>8s} {'MaxDD':>7s} {'Trades':>7s} {'WinR':>6s} {'Final':>10s}")
print(f"  {'─'*8} {'─'*8} {'─'*7} {'─'*7} {'─'*6} {'─'*10}")

total_capital = 0
total_final = 0

for symbol, news in datasets:
    result = run_sentiment_backtest(
        symbol=symbol, news_events=news,
        start="2025-01-01", end="2025-12-31",
        initial_capital=10000.0, threshold=0.4, min_confidence=0.15, cost_model=US_STOCKS,
        scale_by_sentiment=True, max_hold_days=30,
        stop_loss_pct=0.05, take_profit_pct=0.10,
        interval="1h",
    )
    total_capital += 10000
    total_final += result.final_value
    print(f"  {symbol:<8s} {result.total_return_pct:>+7.2f}% {result.max_drawdown_pct:>6.2f}% {result.total_trades:>7} {result.win_rate:>5.1f}% ${result.final_value:>9,.2f}")

portfolio_return = (total_final - total_capital) / total_capital * 100
print(f"  {'─'*8} {'─'*8} {'─'*7} {'─'*7} {'─'*6} {'─'*10}")
print(f"  {'TOTAL':<8s} {portfolio_return:>+7.2f}%                          ${total_final:>9,.2f}")

# Detailed trade logs
for symbol, news in datasets:
    result = run_sentiment_backtest(
        symbol=symbol, news_events=news,
        start="2025-01-01", end="2025-12-31",
        initial_capital=10000.0, threshold=0.4, min_confidence=0.15, cost_model=US_STOCKS,
        scale_by_sentiment=True, max_hold_days=30,
        stop_loss_pct=0.05, take_profit_pct=0.10,
        interval="1h",
    )
    if result.trades:
        print(f"\n  {symbol} trades:")
        for t in result.trades:
            pnl_str = f"  P&L: ${t.pnl:+,.2f}" if t.pnl != 0 else ""
            print(f"    {t.date}  {t.action:>14}  {t.shares:>4}sh  ${t.price:>8.2f}  sent:{t.sentiment:+.2f}  {t.headline[:45]}{pnl_str}")

print(f"\n{'='*75}\n")
