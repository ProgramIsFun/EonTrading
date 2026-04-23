"""Backtest sentiment strategy against historical price data with synthetic news."""
import pandas as pd
import yfinance as yf
from dataclasses import dataclass, field
from datetime import datetime
from ..common.events import NewsEvent
from ..strategies.sentiment import KeywordSentimentAnalyzer, BaseSentimentAnalyzer
from ..common.costs import CostModel, ZERO


@dataclass
class SentimentTrade:
    symbol: str
    action: str  # "buy" or "sell"
    date: object
    price: float
    sentiment: float
    headline: str
    pnl: float = 0.0


@dataclass
class SentimentBacktestResult:
    symbol: str
    initial_capital: float
    final_value: float
    total_return_pct: float
    max_drawdown_pct: float
    total_trades: int
    win_rate: float
    trades: list = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    def summary(self) -> str:
        return (
            f"Sentiment Backtest: {self.symbol}\n"
            f"  Return: {self.total_return_pct:+.2f}%\n"
            f"  Max DD: {self.max_drawdown_pct:.2f}%\n"
            f"  Trades: {self.total_trades} | Win rate: {self.win_rate:.1f}%\n"
            f"  Final: ${self.final_value:,.2f}"
        )


def fetch_prices(symbol: str, start: str, end: str) -> pd.DataFrame:
    """Fetch daily OHLCV from yfinance."""
    df = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    df = df.reset_index()
    df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
    return df


def run_sentiment_backtest(
    symbol: str,
    news_events: list[dict],  # [{"date": "2026-01-15", "headline": "...", "body": "..."}, ...]
    start: str = "2025-01-01",
    end: str = "2026-01-01",
    initial_capital: float = 10000.0,
    threshold: float = 0.5,
    min_confidence: float = 0.3,
    analyzer: BaseSentimentAnalyzer = None,
    cost_model: CostModel = ZERO,
) -> SentimentBacktestResult:
    analyzer = analyzer or KeywordSentimentAnalyzer()
    prices = fetch_prices(symbol, start, end)
    if prices.empty:
        raise ValueError(f"No price data for {symbol}")

    # Index prices by date string for lookup
    prices["date_str"] = prices["date"].dt.strftime("%Y-%m-%d")
    price_map = dict(zip(prices["date_str"], prices["close"]))
    dates_sorted = sorted(price_map.keys())

    def next_trading_day(date_str):
        for d in dates_sorted:
            if d >= date_str:
                return d
        return None

    # Analyze all news events
    signals = []
    for ev in news_events:
        news = NewsEvent(
            source="backtest", headline=ev["headline"],
            timestamp=ev["date"], body=ev.get("body", ""),
        )
        result = analyzer.analyze(news)
        if result.confidence >= min_confidence and symbol in result.symbols:
            trade_date = next_trading_day(ev["date"])
            if trade_date:
                signals.append({
                    "date": trade_date,
                    "sentiment": result.sentiment,
                    "headline": ev["headline"],
                })

    # Simulate trades
    cash = initial_capital
    shares = 0
    entry_price = 0.0
    trades = []
    equity = []

    for _, row in prices.iterrows():
        date_str = row["date_str"]
        price = row["close"]

        # Check for signals on this date
        for sig in signals:
            if sig["date"] != date_str:
                continue
            if sig["sentiment"] >= threshold and shares == 0:
                shares = int(cash / price)
                if shares > 0:
                    cost = cost_model.buy_cost(price, shares)
                    cash -= shares * price + cost
                    entry_price = price
                    trades.append(SentimentTrade(
                        symbol=symbol, action="buy", date=date_str,
                        price=price, sentiment=sig["sentiment"],
                        headline=sig["headline"],
                    ))
            elif sig["sentiment"] <= -threshold and shares > 0:
                cost = cost_model.sell_cost(price, shares)
                pnl = (price - entry_price) * shares - cost
                cash += shares * price - cost
                trades.append(SentimentTrade(
                    symbol=symbol, action="sell", date=date_str,
                    price=price, sentiment=sig["sentiment"],
                    headline=sig["headline"], pnl=pnl,
                ))
                shares = 0

        equity.append(cash + shares * price)

    # Close open position at end
    if shares > 0:
        last_price = prices["close"].iloc[-1]
        pnl = (last_price - entry_price) * shares
        cash += shares * last_price
        trades.append(SentimentTrade(
            symbol=symbol, action="sell (close)", date=dates_sorted[-1],
            price=last_price, sentiment=0, headline="End of backtest", pnl=pnl,
        ))
        shares = 0

    final_value = cash
    equity_series = pd.Series(equity, index=prices.index)
    total_return = (final_value - initial_capital) / initial_capital * 100
    peak = equity_series.expanding().max()
    max_dd = abs(((equity_series - peak) / peak * 100).min())
    sell_trades = [t for t in trades if t.action.startswith("sell")]
    wins = sum(1 for t in sell_trades if t.pnl > 0)
    win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0

    return SentimentBacktestResult(
        symbol=symbol, initial_capital=initial_capital,
        final_value=final_value, total_return_pct=total_return,
        max_drawdown_pct=max_dd, total_trades=len(trades),
        win_rate=win_rate, trades=trades, equity_curve=equity_series,
    )
