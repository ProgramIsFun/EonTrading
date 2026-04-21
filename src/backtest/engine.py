"""Backtesting engine."""
import pandas as pd
from dataclasses import dataclass, field
from ..strategies.base_strategy import Strategy
from ..common.costs import CostModel, ZERO


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
    cost_model: str
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
    position_size: float = 1.0,  # fraction of capital per trade
) -> BacktestResult:
    """
    Run a backtest on OHLCV data with a strategy.
    df must have columns: timestamp, open, high, low, close, volume
    """
    signals = strategy.generate_signals(df)

    cash = initial_capital
    shares = 0
    position = 0  # 0=flat, 1=long
    trades = []
    equity = []
    total_costs = 0.0
    entry_price = 0.0

    for i in range(len(df)):
        price = df["close"].iloc[i]
        sig = signals.iloc[i]

        # Buy
        if sig == 1 and position == 0:
            buy_price = cost_model.effective_buy_price(price)
            shares = int((cash * position_size) / buy_price)
            if shares > 0:
                cost = cost_model.buy_cost(price, shares)
                cash -= shares * price + cost
                total_costs += cost
                position = 1
                entry_price = price

        # Sell
        elif sig == -1 and position == 1:
            sell_price = cost_model.effective_sell_price(price)
            cost = cost_model.sell_cost(price, shares)
            proceeds = shares * price - cost
            pnl = proceeds - (shares * entry_price)
            trades.append({"entry": entry_price, "exit": price, "shares": shares, "pnl": pnl})
            cash += proceeds
            total_costs += cost
            shares = 0
            position = 0

        equity.append(cash + shares * price)

    # Close open position at end
    if position == 1:
        price = df["close"].iloc[-1]
        cost = cost_model.sell_cost(price, shares)
        proceeds = shares * price - cost
        pnl = proceeds - (shares * entry_price)
        trades.append({"entry": entry_price, "exit": price, "shares": shares, "pnl": pnl})
        cash += proceeds
        total_costs += cost
        shares = 0

    final_value = cash
    equity_series = pd.Series(equity, index=df.index)

    # Metrics
    total_return = (final_value - initial_capital) / initial_capital * 100
    days = (df["timestamp"].iloc[-1] - df["timestamp"].iloc[0]).days
    years = max(days / 365.25, 0.01)
    annual_return = ((final_value / initial_capital) ** (1 / years) - 1) * 100

    # Max drawdown
    peak = equity_series.expanding().max()
    drawdown = (equity_series - peak) / peak * 100
    max_dd = abs(drawdown.min())

    # Win rate
    wins = sum(1 for t in trades if t["pnl"] > 0)
    win_rate = (wins / len(trades) * 100) if trades else 0

    # Sharpe (daily returns, annualized)
    daily_returns = equity_series.pct_change().dropna()
    sharpe = (daily_returns.mean() / daily_returns.std() * (252 ** 0.5)) if daily_returns.std() > 0 else 0

    return BacktestResult(
        strategy=strategy.name(),
        symbol=symbol,
        initial_capital=initial_capital,
        final_value=final_value,
        total_return_pct=total_return,
        annual_return_pct=annual_return,
        max_drawdown_pct=max_dd,
        total_trades=len(trades),
        win_rate=win_rate,
        sharpe_ratio=sharpe,
        cost_model=f"{cost_model}",
        total_costs=total_costs,
        trades=trades,
        equity_curve=equity_series,
    )
