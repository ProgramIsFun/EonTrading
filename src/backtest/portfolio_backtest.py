"""Multi-symbol sentiment backtest — single news feed, shared capital, multiple positions."""
import pandas as pd
import yfinance as yf
from dataclasses import dataclass, field
from ..common.events import NewsEvent
from ..strategies.sentiment import KeywordSentimentAnalyzer, BaseSentimentAnalyzer
from ..common.costs import CostModel, ZERO
from ..common.trading_logic import TradingLogic, PositionState


@dataclass
class Trade:
    symbol: str
    action: str
    date: str
    price: float
    sentiment: float
    headline: str
    shares: int = 0
    pnl: float = 0.0


@dataclass
class Position:
    symbol: str
    shares: int
    entry_price: float
    entry_bar: int
    state: PositionState = None  # shared trading logic state

    def __post_init__(self):
        if self.state is None:
            self.state = PositionState(self.symbol, self.shares, self.entry_price)


@dataclass
class PortfolioResult:
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
            f"Portfolio Backtest\n"
            f"  Return: {self.total_return_pct:+.2f}%\n"
            f"  Max DD: {self.max_drawdown_pct:.2f}%\n"
            f"  Trades: {self.total_trades} | Win rate: {self.win_rate:.1f}%\n"
            f"  Final: ${self.final_value:,.2f}"
        )


def _fetch_hourly(symbol, start, end):
    try:
        df = yf.download(symbol, start=start, end=end, interval="1h", auto_adjust=True, progress=False)
        if not df.empty:
            return df
    except Exception:
        pass
    return yf.download(symbol, start=start, end=end, interval="1d", auto_adjust=True, progress=False)


def run_portfolio_backtest(
    news_events: list[dict],
    start: str = "2025-01-01",
    end: str = "2026-01-01",
    initial_capital: float = 70000.0,
    threshold: float = 0.5,
    min_confidence: float = 0.15,
    analyzer: BaseSentimentAnalyzer = None,
    cost_model: CostModel = ZERO,
    max_allocation: float = 0.2,
    risk_per_trade: float = 0.0,
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.10,
    trailing_sl: bool = False,
    max_hold_days: int = 30,
    cooldown_days: int = 1,
) -> PortfolioResult:
    analyzer = analyzer or KeywordSentimentAnalyzer()
    logic = TradingLogic(
        threshold=threshold, min_confidence=min_confidence,
        stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
        trailing_sl=trailing_sl, max_allocation=max_allocation,
        risk_per_trade=risk_per_trade,
    )

    # Analyze all news → list of (timestamp, symbols, sentiment, headline)
    signals = []
    for ev in news_events:
        news = NewsEvent(source="backtest", headline=ev["headline"],
                         timestamp=ev["date"], body=ev.get("body", ""))
        result = analyzer.analyze(news)
        if result.confidence >= min_confidence and result.symbols:
            signals.append({
                "date": ev["date"],
                "symbols": result.symbols,
                "sentiment": result.sentiment,
                "headline": ev["headline"],
            })
    signals.sort(key=lambda s: s["date"])

    # Collect all symbols we need prices for
    all_symbols = set()
    for sig in signals:
        all_symbols.update(sig["symbols"])
    if not all_symbols:
        return PortfolioResult(initial_capital=initial_capital, final_value=initial_capital,
                               total_return_pct=0, max_drawdown_pct=0, total_trades=0, win_rate=0)

    # Fetch prices for all symbols
    print(f"  Fetching prices for {len(all_symbols)} symbols: {', '.join(sorted(all_symbols))}")
    price_data = {}
    for sym in all_symbols:
        df = _fetch_hourly(sym, start, end)
        if df.empty:
            continue
        df = df.reset_index()
        df.columns = [c.lower() if isinstance(c, str) else c[0].lower() for c in df.columns]
        if "datetime" in df.columns:
            df = df.rename(columns={"datetime": "ts"})
        elif "date" in df.columns:
            df = df.rename(columns={"date": "ts"})
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        price_data[sym] = df

    # Build unified timeline (all unique timestamps across all symbols)
    all_ts = set()
    for df in price_data.values():
        all_ts.update(df["ts"].values)
    timeline = sorted(all_ts)

    # Build signal map: timestamp → signal
    signal_map = {}
    for sig in signals:
        ts_str = sig["date"]
        ts = pd.Timestamp(ts_str, tz="UTC") if "T" in ts_str else pd.Timestamp(ts_str + "T09:30:00", tz="UTC")
        ts_val = ts.to_numpy()
        # Find next bar after news
        idx = pd.Index(timeline).searchsorted(ts_val, side="right")
        if idx < len(timeline):
            bar_ts = timeline[idx]
            if bar_ts not in signal_map or abs(sig["sentiment"]) > abs(signal_map[bar_ts]["sentiment"]):
                signal_map[bar_ts] = sig

    # Price lookup helper
    def get_price(symbol, ts, col="open"):
        df = price_data.get(symbol)
        if df is None:
            return None
        ts_aware = pd.Timestamp(ts, tz="UTC")
        idx = df["ts"].searchsorted(ts_aware)
        if idx >= len(df):
            idx = len(df) - 1
        row = df.iloc[idx]
        return float(row[col]) if abs((row["ts"] - ts_aware).total_seconds()) < 7200 else None

    def get_bar(symbol, ts):
        df = price_data.get(symbol)
        if df is None:
            return None
        ts_aware = pd.Timestamp(ts, tz="UTC")
        idx = df["ts"].searchsorted(ts_aware)
        if idx >= len(df):
            idx = len(df) - 1
        row = df.iloc[idx]
        if abs((row["ts"] - ts_aware).total_seconds()) < 7200:
            return row
        return None

    # Simulate
    cash = initial_capital
    positions: dict[str, Position] = {}
    trades = []
    equity = []
    last_trade_ts = {}
    bars_per_day = 7

    for bar_idx, ts in enumerate(timeline):
        ts_str = str(pd.Timestamp(ts))[:19]

        # Check SL/TP/expiry on all positions
        for sym in list(positions.keys()):
            pos = positions[sym]
            bar = get_bar(sym, ts)
            if bar is None:
                continue
            price = float(bar["close"])
            low = float(bar["low"]) if "low" in bar else price
            high = float(bar["high"]) if "high" in bar else price

            closed = False
            # Update peak price for trailing SL
            logic.update_peak(pos.state, high)

            sl_price = logic.check_stop_loss(pos.state, low)
            if sl_price is not None:
                cost = cost_model.sell_cost(sl_price, pos.shares)
                pnl = (sl_price - pos.entry_price) * pos.shares - cost
                cash += pos.shares * sl_price - cost
                trades.append(Trade(sym, "sell (SL)", ts_str, sl_price, 0, "Stop loss", pos.shares, pnl))
                closed = True
            else:
                tp_price = logic.check_take_profit(pos.state, high)
                if tp_price is not None:
                    cost = cost_model.sell_cost(tp_price, pos.shares)
                    pnl = (tp_price - pos.entry_price) * pos.shares - cost
                    cash += pos.shares * tp_price - cost
                    trades.append(Trade(sym, "sell (TP)", ts_str, tp_price, 0, "Take profit", pos.shares, pnl))
                    closed = True
            if not closed and max_hold_days > 0 and (bar_idx - pos.entry_bar) >= max_hold_days * bars_per_day:
                exec_p = float(bar["open"])
                cost = cost_model.sell_cost(exec_p, pos.shares)
                pnl = (exec_p - pos.entry_price) * pos.shares - cost
                cash += pos.shares * exec_p - cost
                trades.append(Trade(sym, "sell (expire)", ts_str, exec_p, 0, "Max hold", pos.shares, pnl))
                closed = True

            if closed:
                del positions[sym]

        # Check signals
        sig = signal_map.get(ts)
        if sig:
            for sym in sig["symbols"]:
                # Cooldown check
                last = last_trade_ts.get(sym, 0)
                if bar_idx - last < cooldown_days * bars_per_day:
                    continue

                if sig["sentiment"] >= threshold and sym not in positions:
                    exec_p = get_price(sym, ts, "open")
                    if exec_p is None:
                        continue
                    buy_shares = logic.should_buy(sig["sentiment"], sig.get("confidence", 1.0), sym, positions, cash, cost_model.effective_buy_price(exec_p))
                    if buy_shares > 0 and buy_shares * exec_p < cash:
                        cost = cost_model.buy_cost(exec_p, buy_shares)
                        cash -= buy_shares * exec_p + cost
                        positions[sym] = Position(sym, buy_shares, exec_p, bar_idx)
                        last_trade_ts[sym] = bar_idx
                        trades.append(Trade(sym, "buy", ts_str, exec_p, sig["sentiment"], sig["headline"], buy_shares))

                elif logic.should_sell_on_sentiment(sig["sentiment"], sig.get("confidence", 1.0), sym, positions):
                    pos = positions[sym]
                    exec_p = get_price(sym, ts, "open")
                    if exec_p is None:
                        continue
                    cost = cost_model.sell_cost(exec_p, pos.shares)
                    pnl = (exec_p - pos.entry_price) * pos.shares - cost
                    cash += pos.shares * exec_p - cost
                    last_trade_ts[sym] = bar_idx
                    trades.append(Trade(sym, "sell", ts_str, exec_p, sig["sentiment"], sig["headline"], pos.shares, pnl))
                    del positions[sym]

        # Portfolio value
        port_value = cash
        for sym, pos in positions.items():
            p = get_price(sym, ts, "close")
            if p:
                port_value += pos.shares * p
        equity.append(port_value)

    # Close remaining positions
    for sym in list(positions.keys()):
        pos = positions[sym]
        df = price_data[sym]
        last_price = float(df["close"].iloc[-1])
        pnl = (last_price - pos.entry_price) * pos.shares
        cash += pos.shares * last_price
        trades.append(Trade(sym, "sell (close)", "end", last_price, 0, "End of backtest", pos.shares, pnl))
        del positions[sym]

    final_value = cash
    equity_series = pd.Series(equity)
    total_return = (final_value - initial_capital) / initial_capital * 100
    peak = equity_series.expanding().max()
    max_dd = abs(((equity_series - peak) / peak * 100).min()) if len(equity_series) > 0 else 0
    sell_trades = [t for t in trades if t.action.startswith("sell")]
    wins = sum(1 for t in sell_trades if t.pnl > 0)
    win_rate = (wins / len(sell_trades) * 100) if sell_trades else 0

    return PortfolioResult(
        initial_capital=initial_capital, final_value=final_value,
        total_return_pct=total_return, max_drawdown_pct=max_dd,
        total_trades=len(trades), win_rate=win_rate,
        trades=trades, equity_curve=equity_series,
    )
