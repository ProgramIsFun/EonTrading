"""Backtesting engine with realistic execution model."""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from ..strategies.base_strategy import Strategy, Signal
from ..common.costs import CostModel, ZERO


@dataclass
class Trade:
    symbol: str
    side: str  # "long" or "short"
    entry_price: float
    exit_price: float
    shares: int
    pnl: float
    entry_date: object = None
    exit_date: object = None


@dataclass
class BacktestResult:
    strategy: str
    symbol: str
    initial_capital: float
    final_value: float
    total_return_pct: float
    annual_return_pct: float
    max_drawdown_pct: float
    total_trades: int
    win_rate: float
    sharpe_ratio: float
    total_costs: float
    trades: list = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=lambda: pd.Series(dtype=float))

    def summary(self) -> str:
        return (
            f"{self.strategy} on {self.symbol}\n"
            f"  Return: {self.total_return_pct:+.2f}% | Annual: {self.annual_return_pct:+.2f}%\n"
            f"  Max DD: {self.max_drawdown_pct:.2f}% | Sharpe: {self.sharpe_ratio:.2f}\n"
            f"  Trades: {self.total_trades} | Win rate: {self.win_rate:.1f}%\n"
            f"  Costs: ${self.total_costs:,.2f} | Final: ${self.final_value:,.2f}"
        )


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    symbol: str = "",
    initial_capital: float = 10000.0,
    cost_model: CostModel = ZERO,
    position_size: float = 1.0,
    allow_short: bool = False,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    exec_next_open: bool = True,
) -> BacktestResult:
    df = df.reset_index(drop=True)
    signals = strategy.generate_signals(df)

    cash = initial_capital
    shares = 0
    position = 0  # 0=flat, 1=long, -1=short
    trades = []
    equity = []
    total_costs = 0.0
    entry_price = 0.0
    entry_date = None
    pending_signal = Signal(0)
    # Per-position SL/TP (from signal or engine defaults)
    pos_sl = 0.0
    pos_tp = 0.0

    def _open_long(price, ts, size):
        nonlocal cash, shares, position, entry_price, entry_date, total_costs, pos_sl, pos_tp
        buy_price = cost_model.effective_buy_price(price)
        shares = int((cash * size) / buy_price)
        if shares > 0:
            cost = cost_model.buy_cost(price, shares)
            cash -= shares * price + cost
            total_costs += cost
            position = 1
            entry_price = price
            entry_date = ts

    def _close_long(price, ts):
        nonlocal cash, shares, position, total_costs
        cost = cost_model.sell_cost(price, shares)
        pnl = (price - entry_price) * shares - cost
        trades.append(Trade(symbol, "long", entry_price, price, shares, pnl, entry_date, ts))
        cash += shares * price - cost
        total_costs += cost
        shares = 0
        position = 0

    def _open_short(price, ts, size):
        nonlocal cash, shares, position, entry_price, entry_date, total_costs, pos_sl, pos_tp
        sell_price = cost_model.effective_sell_price(price)
        shares = int((cash * size) / sell_price)
        if shares > 0:
            cost = cost_model.sell_cost(price, shares)
            cash += shares * price - cost
            total_costs += cost
            position = -1
            entry_price = price
            entry_date = ts

    def _close_short(price, ts):
        nonlocal cash, shares, position, total_costs
        cost = cost_model.buy_cost(price, abs(shares))
        pnl = (entry_price - price) * abs(shares) - cost
        trades.append(Trade(symbol, "short", entry_price, price, abs(shares), pnl, entry_date, ts))
        cash += pnl + entry_price * abs(shares)
        total_costs += cost
        shares = 0
        position = 0

    for i in range(len(df)):
        price_open = df["open"].iloc[i]
        price_high = df["high"].iloc[i]
        price_low = df["low"].iloc[i]
        price_close = df["close"].iloc[i]
        ts = df["timestamp"].iloc[i]

        # --- Execute pending signal at this bar's open ---
        if exec_next_open and pending_signal.action != 0:
            sig = pending_signal
            size = sig.size if sig.size != 1.0 else position_size
            new_sl = sig.stop_loss if sig.stop_loss > 0 else stop_loss_pct
            new_tp = sig.take_profit if sig.take_profit > 0 else take_profit_pct

            if sig.action == 1 and position <= 0:
                if position == -1:
                    _close_short(price_open, ts)
                _open_long(price_open, ts, size)
                pos_sl, pos_tp = new_sl, new_tp

            elif sig.action == -1 and position >= 0:
                if position == 1:
                    _close_long(price_open, ts)
                if allow_short:
                    _open_short(price_open, ts, size)
                    pos_sl, pos_tp = new_sl, new_tp

            pending_signal = Signal(0)

        # --- Check stop-loss / take-profit using intraday high/low ---
        if position == 1 and entry_price > 0:
            if pos_sl > 0 and price_low <= entry_price * (1 - pos_sl):
                _close_long(entry_price * (1 - pos_sl), ts)
            elif pos_tp > 0 and price_high >= entry_price * (1 + pos_tp):
                _close_long(entry_price * (1 + pos_tp), ts)

        elif position == -1 and entry_price > 0:
            if pos_sl > 0 and price_high >= entry_price * (1 + pos_sl):
                _close_short(entry_price * (1 + pos_sl), ts)
            elif pos_tp > 0 and price_low <= entry_price * (1 - pos_tp):
                _close_short(entry_price * (1 - pos_tp), ts)

        # --- Record signal ---
        raw = signals.iloc[i]
        if exec_next_open:
            pending_signal = Signal.from_value(raw)
        else:
            sig = Signal.from_value(raw)
            size = sig.size if sig.size != 1.0 else position_size
            if sig.action == 1 and position == 0:
                _open_long(price_close, ts, size)
                pos_sl = sig.stop_loss if sig.stop_loss > 0 else stop_loss_pct
                pos_tp = sig.take_profit if sig.take_profit > 0 else take_profit_pct
            elif sig.action == -1 and position == 1:
                _close_long(price_close, ts)

        # --- Portfolio value ---
        if position == 1:
            equity.append(cash + shares * price_close)
        elif position == -1:
            equity.append(cash + (entry_price - price_close) * abs(shares))
        else:
            equity.append(cash)

    # Close open position at end
    if position != 0:
        price = df["close"].iloc[-1]
        ts = df["timestamp"].iloc[-1]
        if position == 1:
            _close_long(price, ts)
        elif position == -1:
            _close_short(price, ts)

    final_value = cash
    equity_series = pd.Series(equity, index=df.index)

    # --- Metrics ---
    total_return = (final_value - initial_capital) / initial_capital * 100
    days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).days
    years = max(days / 365.25, 0.01)
    annual_return = ((final_value / initial_capital) ** (1 / years) - 1) * 100 if final_value > 0 else -100

    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak * 100
    max_dd = abs(drawdown.min())

    wins = sum(1 for t in trades if t.pnl > 0)
    win_rate = (wins / len(trades) * 100) if trades else 0

    daily_returns = equity_series.pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * (252 ** 0.5)) if daily_returns.std() > 0 else 0

    return BacktestResult(
        strategy=strategy.name(), symbol=symbol,
        initial_capital=initial_capital, final_value=final_value,
        total_return_pct=total_return, annual_return_pct=annual_return,
        max_drawdown_pct=max_dd, total_trades=len(trades),
        win_rate=win_rate, sharpe_ratio=sharpe,
        total_costs=total_costs, trades=trades, equity_curve=equity_series,
    )
