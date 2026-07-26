"""Backtest sentiment strategy against historical price data with synthetic news."""
import logging
from typing import Any

import pandas as pd
import yfinance as yf

from ..common.costs import ZERO, CostModel
from ..common.events import NewsEvent
from ..common.trading_logic import PositionState, TradingLogic
from ..data.ingest.yfinance_ingest import normalize_yfinance_df
from . import BacktestResultBase, SentimentTrade
from .engine import compute_backtest_metrics
from ..strategies.sentiment import BaseSentimentAnalyzer, KeywordSentimentAnalyzer

logger = logging.getLogger(__name__)


def fetch_prices(symbol: str, start: str, end: str, interval: str = "1h") -> pd.DataFrame:
    """Fetch price data. Tries requested interval, falls back to daily."""
    df = None
    if interval != "1d":
        try:
            df = yf.download(symbol, start=start, end=end, interval=interval, auto_adjust=True, progress=False)
            if df.empty:
                df = None
        except Exception:
            logger.debug("Interval %s unavailable for %s, falling back to 1d", interval, symbol)
            df = None
    if df is None:
        df = yf.download(symbol, start=start, end=end, interval="1d", auto_adjust=True, progress=False)
        interval = "1d"
    df = df.reset_index()
    df = normalize_yfinance_df(df, date_column="timestamp")
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
    analyzer: BaseSentimentAnalyzer | None = None,
    cost_model: CostModel = ZERO,
    # Position sizing
    scale_by_sentiment: bool = True,
    max_allocation: float = 0.0,     # max % of capital per trade (0=off, e.g. 0.3=30%)
    risk_per_trade: float = 0.0,     # max % of capital to risk per trade (0=off, e.g. 0.02=2%)
    # Risk management
    max_hold_days: int = 0,
    cooldown_days: int = 1,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    interval: str = "1h",
) -> BacktestResultBase:
    analyzer = analyzer or KeywordSentimentAnalyzer()
    logic = TradingLogic(
        threshold=threshold, min_confidence=min_confidence,
        stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
        scale_by_sentiment=scale_by_sentiment,
        max_allocation=max_allocation, risk_per_trade=risk_per_trade,
    )
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
        """Return index of the NEXT bar after news timestamp (execute next bar's open)."""
        ts = pd.Timestamp(news_ts, tz="UTC") if "T" in news_ts else pd.Timestamp(news_ts + "T09:30:00", tz="UTC")
        ts_val = ts.to_numpy()
        idx = timestamps.searchsorted(ts_val, side="right")  # next bar after news
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
    signal_map: dict[int, dict[str, Any]] = {}
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
    pos_state: PositionState | None = None

    for i in range(len(prices)):
        row = prices.iloc[i]
        exec_price = row["open"]   # execute at bar's open (more realistic)
        price = row["close"]       # use close for equity/SL/TP checks
        ts = str(row["timestamp"])[:19]

        # Check stop-loss / take-profit using TradingLogic
        if shares > 0 and pos_state is not None:
            bar_low = row["low"] if "low" in row else price
            bar_high = row["high"] if "high" in row else price
            logic.update_peak(pos_state, bar_high)

            sl_price = logic.check_stop_loss(pos_state, bar_low)
            if sl_price is not None:
                cost = cost_model.sell_cost(sl_price, shares)
                pnl = (sl_price - entry_price) * shares - cost
                cash += shares * sl_price - cost
                trades.append(SentimentTrade(
                    symbol=symbol, action="sell (SL)", date=ts,
                    price=sl_price, sentiment=0, headline="Stop loss hit",
                    shares=shares, pnl=pnl,
                ))
                shares = 0
                pos_state = None
            else:
                tp_price = logic.check_take_profit(pos_state, bar_high)
                if tp_price is not None:
                    cost = cost_model.sell_cost(tp_price, shares)
                    pnl = (tp_price - entry_price) * shares - cost
                    cash += shares * tp_price - cost
                    trades.append(SentimentTrade(
                        symbol=symbol, action="sell (TP)", date=ts,
                        price=tp_price, sentiment=0, headline="Take profit hit",
                        shares=shares, pnl=pnl,
                    ))
                    shares = 0
                    pos_state = None

            # Max hold period
            if max_hold_days > 0 and shares > 0 and (i - entry_bar_idx) >= max_hold_bars:
                cost = cost_model.sell_cost(exec_price, shares)
                pnl = (exec_price - entry_price) * shares - cost
                cash += shares * exec_price - cost
                trades.append(SentimentTrade(
                    symbol=symbol, action="sell (expire)", date=ts,
                    price=price, sentiment=0, headline="Max hold reached",
                    shares=shares, pnl=pnl,
                ))
                shares = 0
                pos_state = None

        # Check signals
        signal: dict[str, Any] | None = signal_map.get(i)
        if signal and (i - last_trade_idx) >= cooldown_bars:
            sent = signal["sentiment"]

            if sent >= threshold and shares == 0:
                size = min(abs(sent), 1.0) if scale_by_sentiment else 1.0
                eff_price = cost_model.effective_buy_price(exec_price)

                # Position sizing: start with sentiment-scaled or full capital
                max_shares = int((cash * size) / eff_price)

                # Cap by max allocation
                if max_allocation > 0:
                    alloc_shares = int((cash * max_allocation) / eff_price)
                    max_shares = min(max_shares, alloc_shares)

                # Cap by risk-per-trade (requires stop loss)
                if risk_per_trade > 0 and stop_loss_pct > 0:
                    risk_shares = int((cash * risk_per_trade) / (exec_price * stop_loss_pct))
                    max_shares = min(max_shares, risk_shares)

                buy_shares = max_shares
                if buy_shares > 0:
                    cost = cost_model.buy_cost(exec_price, buy_shares)
                    cash -= buy_shares * exec_price + cost
                    shares = buy_shares
                    entry_price = exec_price
                    entry_bar_idx = i
                    last_trade_idx = i
                    pos_state = PositionState(symbol=symbol, shares=buy_shares, entry_price=exec_price)
                    trades.append(SentimentTrade(
                        symbol=symbol, action="buy", date=ts,
                        price=exec_price, sentiment=sent, headline=signal["headline"],
                        shares=buy_shares,
                    ))

            elif sent <= -threshold and shares > 0:
                cost = cost_model.sell_cost(exec_price, shares)
                pnl = (exec_price - entry_price) * shares - cost
                cash += shares * exec_price - cost
                last_trade_idx = i
                trades.append(SentimentTrade(
                    symbol=symbol, action="sell", date=ts,
                    price=exec_price, sentiment=sent, headline=signal["headline"],
                    shares=shares, pnl=pnl,
                ))
                shares = 0
                pos_state = None

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

    metrics = compute_backtest_metrics(
        equity, initial_capital, trades,
        wins_filter=lambda t: [x for x in t if x.action.startswith("sell")],
        index=prices.index,
    )

    return BacktestResultBase(
        initial_capital=initial_capital, **metrics, trades=trades,
    )
