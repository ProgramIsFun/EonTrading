from dataclasses import dataclass

from .engine import BacktestResult, BacktestResultBase, compute_backtest_metrics, run_backtest


@dataclass
class SentimentTrade:
    """Shared trade record for sentiment-based backtests."""
    symbol: str
    action: str
    date: object
    price: float
    sentiment: float
    headline: str
    shares: int = 0
    pnl: float = 0.0
