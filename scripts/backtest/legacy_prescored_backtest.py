#!/usr/bin/env python3
"""Portfolio backtest with pre-scored events — includes SL/TP, trailing SL, costs."""
from src.backtest.portfolio_backtest import run_portfolio_backtest
from src.common.clock import utcnow
from src.common.costs import US_STOCKS
from src.common.events import NewsEvent, SentimentEvent
from src.strategies.sentiment import BaseSentimentAnalyzer


class PreScoredAnalyzer(BaseSentimentAnalyzer):
    """Passthrough analyzer — returns scores embedded in the news body as JSON."""

    def __init__(self, scores: dict):
        # scores: {headline: {symbols, sentiment, confidence}}
        self.scores = scores

    def analyze(self, event: NewsEvent, positions: dict = None) -> SentimentEvent:
        score = self.scores.get(event.headline, {})
        return SentimentEvent(
            source=event.source, headline=event.headline,
            timestamp=event.timestamp,
            analyzed_at=utcnow().isoformat() + "Z",
            symbols=score.get("symbols", []),
            sentiment=score.get("sentiment", 0),
            confidence=score.get("confidence", 0),
            urgency=score.get("urgency", "normal"),
        )


# Pre-scored real events — same as replay backtest
EVENTS = [
    {"date": "2025-01-06T10:00:00", "headline": "Nvidia unveils Blackwell GPU at CES", "symbols": ["NVDA"], "sentiment": 0.8, "confidence": 0.9},
    {"date": "2025-01-27T09:30:00", "headline": "DeepSeek AI shocks market, Nvidia crashes", "symbols": ["NVDA"], "sentiment": -0.9, "confidence": 0.95},
    {"date": "2025-01-29T16:30:00", "headline": "Meta Q4 earnings beat, ad revenue accelerates", "symbols": ["META"], "sentiment": 0.8, "confidence": 0.9},
    {"date": "2025-01-30T16:30:00", "headline": "Apple reports record Q1 revenue $124B", "symbols": ["AAPL"], "sentiment": 0.7, "confidence": 0.85},
    {"date": "2025-02-06T16:30:00", "headline": "Amazon Q4 earnings beat, AWS growth accelerates", "symbols": ["AMZN"], "sentiment": 0.7, "confidence": 0.85},
    {"date": "2025-02-14T10:00:00", "headline": "Meta $65B AI spending, stock drops on cost fears", "symbols": ["META"], "sentiment": -0.7, "confidence": 0.85},
    {"date": "2025-02-26T16:30:00", "headline": "Nvidia Q4 earnings smash records, data center +93%", "symbols": ["NVDA"], "sentiment": 0.9, "confidence": 0.95},
    {"date": "2025-03-12T10:00:00", "headline": "Google acquires Wiz for $32B", "symbols": ["GOOGL"], "sentiment": 0.6, "confidence": 0.7},
    {"date": "2025-03-24T10:00:00", "headline": "Musk promises affordable Tesla under $30K", "symbols": ["TSLA"], "sentiment": 0.6, "confidence": 0.7},
    {"date": "2025-04-03T14:00:00", "headline": "Trump sweeping tariffs on China", "symbols": ["AAPL", "NVDA", "AMZN", "META", "MSFT", "GOOGL"], "sentiment": -0.9, "confidence": 0.95},
    {"date": "2025-04-09T15:00:00", "headline": "Trump pauses tariffs 90 days", "symbols": ["AAPL", "NVDA", "AMZN"], "sentiment": 0.7, "confidence": 0.8},
    {"date": "2025-04-22T16:30:00", "headline": "Tesla Q1 earnings plunge 71%", "symbols": ["TSLA"], "sentiment": -0.8, "confidence": 0.9},
    {"date": "2025-04-23T10:00:00", "headline": "Musk to reduce DOGE role, focus on Tesla", "symbols": ["TSLA"], "sentiment": 0.8, "confidence": 0.85},
    {"date": "2025-04-24T16:30:00", "headline": "Alphabet Q1 earnings beat, cloud surges", "symbols": ["GOOGL"], "sentiment": 0.7, "confidence": 0.85},
    {"date": "2025-04-30T16:30:00", "headline": "Meta Q1 earnings crush, revenue +16%", "symbols": ["META"], "sentiment": 0.8, "confidence": 0.9},
    {"date": "2025-04-30T16:30:00", "headline": "Microsoft Q3 crush, Azure 35%", "symbols": ["MSFT"], "sentiment": 0.8, "confidence": 0.9},
    {"date": "2025-05-01T16:30:00", "headline": "Apple Q2 earnings beat, services record", "symbols": ["AAPL"], "sentiment": 0.7, "confidence": 0.8},
    {"date": "2025-05-01T16:30:00", "headline": "Amazon weak Q2 guidance drops stock", "symbols": ["AMZN"], "sentiment": -0.5, "confidence": 0.7},
]

# Build score lookup
scores = {ev["headline"]: ev for ev in EVENTS}
analyzer = PreScoredAnalyzer(scores)

# Convert to news format
news_events = [{"date": ev["date"], "headline": ev["headline"]} for ev in EVENTS]

configs = [
    {"label": "No SL/TP", "stop_loss_pct": 0, "take_profit_pct": 0, "trailing_sl": False},
    {"label": "SL 5% / TP 10%", "stop_loss_pct": 0.05, "take_profit_pct": 0.10, "trailing_sl": False},
    {"label": "Trailing SL 5% / TP 10%", "stop_loss_pct": 0.05, "take_profit_pct": 0.10, "trailing_sl": True},
    {"label": "Trailing SL 8% / TP 15%", "stop_loss_pct": 0.08, "take_profit_pct": 0.15, "trailing_sl": True},
]

print("\n" + "=" * 75)
print("  Pre-scored portfolio backtest — with SL/TP simulation")
print("=" * 75)
print(f"\n  {'Config':<30s} {'Return':>8s} {'MaxDD':>7s} {'Trades':>7s} {'WinR':>6s} {'Final':>10s}")
print(f"  {'─'*30} {'─'*8} {'─'*7} {'─'*7} {'─'*6} {'─'*10}")

for cfg in configs:
    result = run_portfolio_backtest(
        news_events=news_events,
        start="2025-01-01", end="2025-12-31",
        initial_capital=70000.0,
        threshold=0.4, min_confidence=0.15,
        analyzer=analyzer,
        cost_model=US_STOCKS,
        max_allocation=0.2,
        stop_loss_pct=cfg["stop_loss_pct"],
        take_profit_pct=cfg["take_profit_pct"],
        trailing_sl=cfg["trailing_sl"],
        max_hold_days=0,
    )
    print(f"  {cfg['label']:<30s} {result.total_return_pct:>+7.2f}% {result.max_drawdown_pct:>6.2f}% {result.total_trades:>7} {result.win_rate:>5.1f}% ${result.final_value:>9,.2f}")

# Show trade log for best config
print("\n  Trade log (Trailing SL 5% / TP 10%):")
result = run_portfolio_backtest(
    news_events=news_events, start="2025-01-01", end="2025-12-31",
    initial_capital=70000.0, threshold=0.4, min_confidence=0.15,
    analyzer=analyzer, cost_model=US_STOCKS, max_allocation=0.2,
    stop_loss_pct=0.05, take_profit_pct=0.10, trailing_sl=True,
)
for t in result.trades:
    pnl_str = f"  P&L: ${t.pnl:+,.2f}" if t.pnl != 0 else ""
    print(f"    {t.date:<22s} {t.action:<14s} {t.shares:>4}sh {t.symbol:<6s} ${t.price:>8.2f}{pnl_str}")

print(f"\n{'='*75}\n")
