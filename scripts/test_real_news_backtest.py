#!/usr/bin/env python3
"""Backtest with real historical news — compare position sizing strategies."""
from src.backtest.sentiment_backtest import run_sentiment_backtest
from src.common.costs import US_STOCKS

# Real news events (same as before)
ALL_NEWS = {
    "AAPL": [
        {"date": "2025-01-30T16:30:00", "headline": "Apple reports record Q1 revenue of $124B, beating estimates"},
        {"date": "2025-03-26T09:30:00", "headline": "Apple loses antitrust case, judge rules App Store violates court order"},
        {"date": "2025-04-03T14:00:00", "headline": "Trump announces sweeping tariffs on China, Apple supply chain at risk"},
        {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs for 90 days, Apple stock surges on relief rally"},
        {"date": "2025-05-01T16:30:00", "headline": "Apple Q2 earnings beat expectations, services revenue hits record"},
        {"date": "2025-06-09T13:00:00", "headline": "Apple announces Apple Intelligence AI features at WWDC 2025"},
    ],
    "TSLA": [
        {"date": "2025-01-29T16:30:00", "headline": "Tesla Q4 earnings miss estimates, revenue falls short of expectations"},
        {"date": "2025-03-03T14:00:00", "headline": "Tesla sales crash in Europe, down 45% amid Musk backlash and boycotts"},
        {"date": "2025-03-24T10:00:00", "headline": "Tesla stock rallies as Musk promises new affordable model under $30K"},
        {"date": "2025-04-22T16:30:00", "headline": "Tesla Q1 earnings plunge 71%, worst quarter in years"},
        {"date": "2025-04-23T10:00:00", "headline": "Elon Musk says he will reduce DOGE role to focus on Tesla, stock surges"},
    ],
    "NVDA": [
        {"date": "2025-01-06T10:00:00", "headline": "Nvidia unveils new Blackwell GPU chips at CES, stock rallies"},
        {"date": "2025-01-27T09:30:00", "headline": "DeepSeek AI model shocks market, Nvidia stock crashes on cheaper AI fears"},
        {"date": "2025-02-26T16:30:00", "headline": "Nvidia Q4 earnings smash records, data center revenue surges 93%"},
        {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs threaten chip exports to China, Nvidia drops sharply"},
        {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs 90 days, Nvidia rallies on trade relief"},
        {"date": "2025-04-15T09:30:00", "headline": "Nvidia announces $500B US AI infrastructure investment plan"},
    ],
    "META": [
        {"date": "2025-01-29T16:30:00", "headline": "Meta Q4 earnings beat estimates, ad revenue growth accelerates"},
        {"date": "2025-02-14T10:00:00", "headline": "Meta announces massive AI spending increase to $65B, stock drops on cost fears"},
        {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs rattle tech sector, Meta falls with broader market decline"},
        {"date": "2025-04-30T16:30:00", "headline": "Meta Q1 earnings crush expectations, revenue up 16% on strong ad demand"},
    ],
    "MSFT": [
        {"date": "2025-01-29T16:30:00", "headline": "Microsoft Q2 earnings beat estimates but Azure growth slows, stock drops"},
        {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs rattle tech sector, Microsoft falls with market decline"},
        {"date": "2025-04-30T16:30:00", "headline": "Microsoft Q3 earnings crush estimates, Azure growth reaccelerates to 35%"},
    ],
    "GOOGL": [
        {"date": "2025-02-04T16:30:00", "headline": "Alphabet Q4 earnings miss on cloud revenue, Google stock drops"},
        {"date": "2025-03-12T10:00:00", "headline": "Google acquires cloud security firm Wiz for $32B, biggest deal ever"},
        {"date": "2025-04-24T16:30:00", "headline": "Alphabet Q1 earnings beat estimates, cloud revenue surges, stock rallies"},
    ],
    "AMZN": [
        {"date": "2025-02-06T16:30:00", "headline": "Amazon Q4 earnings beat estimates, AWS revenue growth accelerates"},
        {"date": "2025-04-03T14:00:00", "headline": "Trump tariffs threaten Amazon e-commerce costs, stock drops sharply"},
        {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs 90 days, Amazon surges on trade relief"},
        {"date": "2025-05-01T16:30:00", "headline": "Amazon Q1 earnings beat, but weak Q2 guidance drops stock"},
    ],
}

configs = [
    {"label": "All-in (current)",       "scale_by_sentiment": True,  "max_allocation": 0,    "risk_per_trade": 0},
    {"label": "Max 30% per trade",      "scale_by_sentiment": True,  "max_allocation": 0.3,  "risk_per_trade": 0},
    {"label": "Risk 2% per trade",      "scale_by_sentiment": False, "max_allocation": 0,    "risk_per_trade": 0.02},
    {"label": "Risk 2% + cap 30%",      "scale_by_sentiment": False, "max_allocation": 0.3,  "risk_per_trade": 0.02},
    {"label": "Risk 5% + cap 50%",      "scale_by_sentiment": False, "max_allocation": 0.5,  "risk_per_trade": 0.05},
]

for cfg in configs:
    total_capital = 0
    total_final = 0
    total_trades = 0
    total_wins = 0

    for symbol, news in ALL_NEWS.items():
        result = run_sentiment_backtest(
            symbol=symbol, news_events=news,
            start="2025-01-01", end="2025-12-31",
            initial_capital=10000.0, threshold=0.4, min_confidence=0.15,
            cost_model=US_STOCKS,
            scale_by_sentiment=cfg["scale_by_sentiment"],
            max_allocation=cfg["max_allocation"],
            risk_per_trade=cfg["risk_per_trade"],
            max_hold_days=30, stop_loss_pct=0.05, take_profit_pct=0.10,
            interval="1h",
        )
        total_capital += 10000
        total_final += result.final_value
        total_trades += result.total_trades
        sell_trades = [t for t in result.trades if t.action.startswith("sell")]
        total_wins += sum(1 for t in sell_trades if t.pnl > 0)

    portfolio_return = (total_final - total_capital) / total_capital * 100
    sell_count = total_trades // 2  # rough: half are buys, half sells
    win_rate = (total_wins / sell_count * 100) if sell_count > 0 else 0
    print(f"  {cfg['label']:<25s}  return: {portfolio_return:>+6.2f}%  trades: {total_trades:>3}  win: {win_rate:>5.1f}%  final: ${total_final:>10,.2f}")
