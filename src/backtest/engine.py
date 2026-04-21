"""Backtesting engine with realistic execution model."""
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from ..strategies.base_strategy import Strategy
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
    stop_loss_pct: float = 0.0,     # 0 = disabled, e.g. 0.05 = 5% stop
    take_profit_pct: float = 0.0,   # 0 = disabled, e.g. 0.10 = 10% take profit
    exec_next_open: bool = True,    # execute on next bar's open (realistic)
) -> BacktestResult:
    """
    Run a backtest on OHLCV data.
    df must have columns: timestamp, open, high, low, close, volume
    """
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
    pending_signal = 0

    for i in range(len(df)):
        price_open = df["open"].iloc[i]
        price_high = df["high"].iloc[i]
        price_low = df["low"].iloc[i]
        price_close = df["close"].iloc[i]
        ts = df["timestamp"].iloc[i]

        # Execute pending signal from previous bar at this bar's open
        if exec_next_open and pending_signal != 0:
            exec_price = price_open

            if pending_signal == 1 and position <= 0:
                # Close short if any
                if position == -1:
                    cost = cost_model.buy_cost(exec_price, abs(shares))
                    pnl = (entry_price - exec_price) * abs(shares) - cost
                    trades.append(Trade(symbol, "short", entry_price, exec_price, abs(shares), pnl, entry_date, ts))
                    cash += pnl + entry_price * abs(shares)
                    total_costs += cost
                    shares = 0
                    position = 0

                # Open long
                buy_price = cost_model.effective_buy_price(exec_price)
                shares = int((cash * position_size) / buy_price)
                if shares > 0:
                    cost = cost_model.buy_cost(exec_price, shares)
                    cash -= shares * exec_price + cost
                    total_costs += cost
                    position = 1
                    entry_price = exec_price
                    entry_date = ts

            elif pending_signal == -1 and position >= 0:
                # Close long if any
                if position == 1:
                    cost = cost_model.sell_cost(exec_price, shares)
                    pnl = (exec_price - entry_price) * shares - cost
                    trades.append(Trade(symbol, "long", entry_price, exec_price, shares, pnl, entry_date, ts))
                    cash += shares * exec_price - cost
                    total_costs += cost
                    shares = 0
                    position = 0

                # Open short
                if allow_short and position == 0:
                    sell_price = cost_model.effective_sell_price(exec_price)
                    shares = int((cash * position_size) / sell_price)
                    if shares > 0:
                        cost = cost_model.sell_cost(exec_price, shares)
                        cash += shares * exec_price - cost
                        total_costs += cost
                        position = -1
                        entry_price = exec_price
                        entry_date = ts

            pending_signal = 0

        # Check stop-loss / take-profit using intraday high/low
        if position == 1 and entry_price > 0:
            if stop_loss_pct > 0 and price_low <= entry_price * (1 - stop_loss_pct):
                exec_price = entry_price * (1 - stop_loss_pct)
                cost = cost_model.sell_cost(exec_price, shares)
                pnl = (exec_price - entry_price) * shares - cost
                trades.append(Trade(symbol, "long", entry_price, exec_price, shares, pnl, entry_date, ts))
                cash += shares * exec_price - cost
                total_costs += cost
                shares = 0
                position = 0
            elif take_profit_pct > 0 and price_high >= entry_price * (1 + take_profit_pct):
                exec_price = entry_price * (1 + take_profit_pct)
                cost = cost_model.sell_cost(exec_price, shares)
                pnl = (exec_price - entry_price) * shares - cost
                trades.append(Trade(symbol, "long", entry_price, exec_price, shares, pnl, entry_date, ts))
                cash += shares * exec_price - cost
                total_costs += cost
                shares = 0
                position = 0

        elif position == -1 and entry_price > 0:
            if stop_loss_pct > 0 and price_high >= entry_price * (1 + stop_loss_pct):
                exec_price = entry_price * (1 + stop_loss_pct)
                cost = cost_model.buy_cost(exec_price, abs(shares))
                pnl = (entry_price - exec_price) * abs(shares) - cost
                trades.append(Trade(symbol, "short", entry_price, exec_price, abs(shares), pnl, entry_date, ts))
                cash += pnl + entry_price * abs(shares)
                total_costs += cost
                shares = 0
                position = 0
            elif take_profit_pct > 0 and price_low <= entry_price * (1 - take_profit_pct):
                exec_price = entry_price * (1 - take_profit_pct)
                cost = cost_model.buy_cost(exec_price, abs(shares))
                pnl = (entry_price - exec_price) * abs(shares) - cost
                trades.append(Trade(symbol, "short", entry_price, exec_price, abs(shares), pnl, entry_date, ts))
                cash += pnl + entry_price * abs(shares)
                total_costs += cost
                shares = 0
                position = 0

        # Record signal for next bar execution
        sig = signals.iloc[i]
        if exec_next_open:
            pending_signal = sig
        else:
            # Legacy: execute at close (less realistic)
            if sig == 1 and position == 0:
                buy_price = cost_model.effective_buy_price(price_close)
                shares = int((cash * position_size) / buy_price)
                if shares > 0:
                    cost = cost_model.buy_cost(price_close, shares)
                    cash -= shares * price_close + cost
                    total_costs += cost
                    position = 1
                    entry_price = price_close
                    entry_date = ts
            elif sig == -1 and position == 1:
                cost = cost_model.sell_cost(price_close, shares)
                pnl = (price_close - entry_price) * shares - cost
                trades.append(Trade(symbol, "long", entry_price, price_close, shares, pnl, entry_date, ts))
                cash += shares * price_close - cost
                total_costs += cost
                shares = 0
                position = 0

        # Portfolio value
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
            cost = cost_model.sell_cost(price, shares)
            pnl = (price - entry_price) * shares - cost
            trades.append(Trade(symbol, "long", entry_price, price, shares, pnl, entry_date, ts))
            cash += shares * price - cost
        elif position == -1:
            cost = cost_model.buy_cost(price, abs(shares))
            pnl = (entry_price - price) * abs(shares) - cost
            trades.append(Trade(symbol, "short", entry_price, price, abs(shares), pnl, entry_date, ts))
            cash += pnl + entry_price * abs(shares)
        total_costs += cost
        shares = 0

    final_value = cash
    equity_series = pd.Series(equity, index=df.index)

    # Metrics
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
