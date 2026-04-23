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
    action: str
    date: object
    price: float
    sentiment: float
    headline: str
    shares: int = 0
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


def fetch_prices(symbol: str, start: str, end: str, interval: str = "1h") -> pd.DataFrame:
    """Fetch price data. Tries requested interval, falls back to daily."""
    df = None
    if interval != "1d":
        try:
            df = yf.download(symbol, start=start, end=end, interval=interval, auto_adjust=True, progress=False)
            if df.empty:
                df = None
        except Exception:
            df = None
    if df is None:
        df = yf.download(symbol, start=start, end=end, interval="1d", auto_adjust=True, progress=False)
        interval = "1d"
    df = df.reset_index()
    # Normalize column names (yfinance returns MultiIndex for single ticker)
    first_col = df.columns[0]
    date_col = first_col if isinstance(first_col, str) else first_col[0]
    df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
    df = df.rename(columns={date_col.lower(): "timestamp"})
    if "datetime" in df.columns:
        df = df.rename(columns={"datetime": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df._interval = interval
    return df


def run_sentiment_backtest(
    symbol: str,
    news_events: list[dict],
    start: str = "2025-01-01",
    end: str = "2026-01-01",
    initial_capital: float = 10000.0,
    threshold: float = 0.5,
    min_confidence: float = 0.3,
    analyzer: BaseSentimentAnalyzer = None,
    cost_model: CostModel = ZERO,
    # New parameters
    scale_by_sentiment: bool = True,
    max_hold_days: int = 0,
    cooldown_days: int = 1,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    interval: str = "1h",
) -> SentimentBacktestResult:
    analyzer = analyzer or KeywordSentimentAnalyzer()
    prices = fetch_prices(symbol, start, end, interval=interval)
    if prices.empty:
        raise ValueError(f"No price data for {symbol}")
    used_interval = getattr(prices, '_interval', interval)
    print(f"  Using {used_interval} data ({len(prices)} bars)")

    # Convert day-based params to bar counts
    bars_per_day = {"1h": 7, "1d": 1}.get(used_interval, 1)
    cooldown_bars = max(cooldown_days * bars_per_day, 1)
    max_hold_bars = max_hold_days * bars_per_day if max_hold_days > 0 else 0

    # Find the nearest bar at or after a given timestamp
    timestamps = prices["timestamp"].values

    def find_bar(news_ts: str) -> int:
        """Return index of nearest bar at or after news timestamp."""
        ts = pd.Timestamp(news_ts, tz="UTC") if "T" in news_ts else pd.Timestamp(news_ts + "T09:30:00", tz="UTC")
        ts_val = ts.to_numpy()
        idx = timestamps.searchsorted(ts_val)
        return int(min(idx, len(prices) - 1))

    # Analyze news and build signal list
    signals = []
    for ev in news_events:
        news = NewsEvent(
            source="backtest", headline=ev["headline"],
            timestamp=ev["date"], body=ev.get("body", ""),
        )
        result = analyzer.analyze(news)
        if result.confidence >= min_confidence and symbol in result.symbols:
            bar_idx = find_bar(ev["date"])
            signals.append({
                "bar_idx": bar_idx,
                "sentiment": result.sentiment,
                "confidence": result.confidence,
                "headline": ev["headline"],
            })

    # Dedup: keep strongest signal per bar
    signal_map = {}
    for sig in signals:
        idx = sig["bar_idx"]
        existing = signal_map.get(idx)
        if not existing or abs(sig["sentiment"]) > abs(existing["sentiment"]):
            signal_map[idx] = sig

    # Simulate
    cash = initial_capital
    shares = 0
    entry_price = 0.0
    entry_bar_idx = 0
    last_trade_idx = -999
    trades = []
    equity = []

    for i in range(len(prices)):
        row = prices.iloc[i]
        price = row["close"]
        ts = str(row["timestamp"])[:19]

        # Check stop-loss / take-profit on open positions
        if shares > 0:
            if stop_loss_pct > 0 and price <= entry_price * (1 - stop_loss_pct):
                sl_price = entry_price * (1 - stop_loss_pct)
                pnl = (sl_price - entry_price) * shares
                cash += shares * sl_price
                trades.append(SentimentTrade(
                    symbol=symbol, action="sell (SL)", date=ts,
                    price=sl_price, sentiment=0, headline="Stop loss hit",
                    shares=shares, pnl=pnl,
                ))
                shares = 0
            elif take_profit_pct > 0 and price >= entry_price * (1 + take_profit_pct):
                tp_price = entry_price * (1 + take_profit_pct)
                pnl = (tp_price - entry_price) * shares
                cash += shares * tp_price
                trades.append(SentimentTrade(
                    symbol=symbol, action="sell (TP)", date=ts,
                    price=tp_price, sentiment=0, headline="Take profit hit",
                    shares=shares, pnl=pnl,
                ))
                shares = 0

            # Max hold period
            if max_hold_days > 0 and shares > 0 and (i - entry_bar_idx) >= max_hold_bars:
                pnl = (price - entry_price) * shares
                cash += shares * price
                trades.append(SentimentTrade(
                    symbol=symbol, action="sell (expire)", date=ts,
                    price=price, sentiment=0, headline=f"Max hold reached",
                    shares=shares, pnl=pnl,
                ))
                shares = 0

        # Check signals
        sig = signal_map.get(i)
        if sig and (i - last_trade_idx) >= cooldown_bars:
            sent = sig["sentiment"]

            if sent >= threshold and shares == 0:
                size = min(abs(sent), 1.0) if scale_by_sentiment else 1.0
                buy_shares = int((cash * size) / price)
                if buy_shares > 0:
                    cost = cost_model.buy_cost(price, buy_shares)
                    cash -= buy_shares * price + cost
                    shares = buy_shares
                    entry_price = price
                    entry_bar_idx = i
                    last_trade_idx = i
                    trades.append(SentimentTrade(
                        symbol=symbol, action="buy", date=ts,
                        price=price, sentiment=sent, headline=sig["headline"],
                        shares=buy_shares,
                    ))

            elif sent <= -threshold and shares > 0:
                cost = cost_model.sell_cost(price, shares)
                pnl = (price - entry_price) * shares - cost
                cash += shares * price - cost
                last_trade_idx = i
                trades.append(SentimentTrade(
                    symbol=symbol, action="sell", date=ts,
                    price=price, sentiment=sent, headline=sig["headline"],
                    shares=shares, pnl=pnl,
                ))
                shares = 0

        equity.append(cash + shares * price)

    # Close open position
    if shares > 0:
        last_price = prices["close"].iloc[-1]
        ts = str(prices["timestamp"].iloc[-1])[:19]
        pnl = (last_price - entry_price) * shares
        cash += shares * last_price
        trades.append(SentimentTrade(
            symbol=symbol, action="sell (close)", date=ts,
            price=last_price, sentiment=0, headline="End of backtest",
            shares=shares, pnl=pnl,
        ))

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
