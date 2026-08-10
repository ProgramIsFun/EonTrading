"""Multi-symbol sentiment backtest — single news feed, shared capital, multiple positions."""
import logging
from dataclasses import dataclass

import pandas as pd

from ..common.costs import ZERO, CostModel
from ..common.events import NewsEvent
from ..common.trading_logic import PositionState, TradingLogic
from . import BacktestResultBase, SentimentTrade
from .engine import check_position_exit, compute_backtest_metrics
from .prices import fetch_price_data
from ..strategies.sentiment import BaseSentimentAnalyzer, KeywordSentimentAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    shares: int
    entry_price: float
    entry_bar: int
    state: PositionState | None = None  # shared trading logic state

    def __post_init__(self):
        if self.state is None:
            self.state = PositionState(self.symbol, self.shares, self.entry_price)


def run_portfolio_backtest(
    news_events: list[dict],
    start: str = "2025-01-01",
    end: str = "2026-01-01",
    initial_capital: float = 70000.0,
    threshold: float = 0.5,
    min_confidence: float = 0.15,
    analyzer: BaseSentimentAnalyzer | None = None,
    cost_model: CostModel = ZERO,
    max_allocation: float = 0.2,
    risk_per_trade: float = 0.0,
    stop_loss_pct: float = 0.05,
    take_profit_pct: float = 0.10,
    trailing_sl: bool = False,
    max_hold_days: int = 30,
    cooldown_days: int = 1,
) -> BacktestResultBase:
    analyzer = analyzer or KeywordSentimentAnalyzer()
    logic = TradingLogic(
        threshold=threshold, min_confidence=min_confidence,
        stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct,
        trailing_sl=trailing_sl, max_allocation=max_allocation,
        risk_per_trade=risk_per_trade,
    )

    # Pre-process news: parse timestamps and sort
    news_queue = []
    for ev in news_events:
        ts_str = ev["date"]
        ts = pd.Timestamp(ts_str, tz="UTC") if "T" in ts_str else pd.Timestamp(ts_str + "T09:30:00", tz="UTC")
        news_queue.append({"ts": ts, "headline": ev["headline"], "body": ev.get("body", ""), "date": ev["date"]})
    news_queue.sort(key=lambda n: n["ts"])

    # First pass: quick analyze without positions to discover which symbols we need prices for
    all_symbols = set()
    for nq in news_queue:
        news = NewsEvent(source="backtest", headline=nq["headline"], timestamp=nq["date"], body=nq["body"])
        result = analyzer.analyze(news)
        if result.confidence >= min_confidence and result.symbols:
            all_symbols.update(result.symbols)
    if not all_symbols:
        return BacktestResultBase(initial_capital=initial_capital, final_value=initial_capital,
                                  total_return_pct=0, max_drawdown_pct=0, total_trades=0, win_rate=0)

    # Fetch prices for all symbols
    print(f"  Fetching prices for {len(all_symbols)} symbols: {', '.join(sorted(all_symbols))}")
    price_data = {}
    for sym in all_symbols:
        df = fetch_price_data(sym, start, end, interval="1h", date_column="ts")
        if df.empty:
            continue
        price_data[sym] = df

    # Build unified timeline
    all_ts = set()
    for df in price_data.values():
        all_ts.update(df["ts"].values)
    timeline = sorted(all_ts)

    # Build news map: bar timestamp → news event (for re-analysis with positions during simulation)
    news_map = {}
    for nq in news_queue:
        ts_val = nq["ts"].to_numpy()
        idx = pd.Index(timeline).searchsorted(ts_val, side="right")
        if idx < len(timeline):
            bar_ts = timeline[idx]
            if bar_ts not in news_map:
                news_map[bar_ts] = nq

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
    last_trade_ts: dict = {}
    bars_per_day = 7

    for bar_idx, ts in enumerate(timeline):
        ts_str = str(pd.Timestamp(ts))[:19]

        # Check SL/TP/expiry on all positions
        for sym in list(positions.keys()):
            pos = positions[sym]
            bar = get_bar(sym, ts)
            if bar is None:
                continue

            assert pos.state is not None
            exit_info = check_position_exit(
                logic, cost_model, pos.state, bar, bar_idx, pos.entry_bar,
                max_hold_days * bars_per_day,
            )
            if exit_info is None:
                continue
            action, exit_price, headline = exit_info
            cost = cost_model.sell_cost(exit_price, pos.shares)
            pnl = (exit_price - pos.entry_price) * pos.shares - cost
            cash += pos.shares * exit_price - cost
            trades.append(SentimentTrade(sym, action, ts_str, exit_price, 0, headline, pos.shares, pnl))
            del positions[sym]

        # Check news — re-analyze with current positions for portfolio-aware scoring
        nq_item = news_map.get(ts)
        if nq_item:
            news = NewsEvent(source="backtest", headline=nq_item["headline"], timestamp=nq_item["date"], body=nq_item["body"])
            sig = analyzer.analyze(news, positions={s: pos.shares for s, pos in positions.items()})
            if sig.confidence >= min_confidence and sig.symbols:
                for sym in sig.symbols:
                    # Cooldown check
                    last = last_trade_ts.get(sym, 0)
                    if bar_idx - last < cooldown_days * bars_per_day:
                        continue

                    if sig.sentiment >= threshold and sym not in positions:
                        exec_p = get_price(sym, ts, "open")
                        if exec_p is None:
                            continue
                        buy_shares = logic.should_buy(sig.sentiment, sig.confidence, sym, positions, cash, exec_p, cost_model=cost_model)
                        if buy_shares > 0:
                            cost = cost_model.buy_cost(exec_p, buy_shares)
                            cash -= buy_shares * exec_p + cost
                            positions[sym] = Position(sym, buy_shares, exec_p, bar_idx)
                            last_trade_ts[sym] = bar_idx
                            trades.append(SentimentTrade(sym, "buy", ts_str, exec_p, sig.sentiment, nq["headline"], buy_shares))

                    elif logic.should_sell_on_sentiment(sig.sentiment, sig.confidence, sym, positions):
                        pos = positions[sym]
                        exec_p = get_price(sym, ts, "open")
                        if exec_p is None:
                            continue
                        cost = cost_model.sell_cost(exec_p, pos.shares)
                        pnl = (exec_p - pos.entry_price) * pos.shares - cost
                        cash += pos.shares * exec_p - cost
                        last_trade_ts[sym] = bar_idx
                        trades.append(SentimentTrade(sym, "sell", ts_str, exec_p, sig.sentiment, nq["headline"], pos.shares, pnl))
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
        trades.append(SentimentTrade(sym, "sell (close)", "end", last_price, 0, "End of backtest", pos.shares, pnl))
        del positions[sym]

    final_value = cash
    equity_series = pd.Series(equity)
    metrics = compute_backtest_metrics(
        equity, initial_capital, trades,
        wins_filter=lambda t: [x for x in t if x.action.startswith("sell")],
    )

    return BacktestResultBase(
        initial_capital=initial_capital, **metrics, trades=trades,
    )
