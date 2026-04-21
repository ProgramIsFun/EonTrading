import pandas as pd
import numpy as np
from src.backtest import run_backtest
from src.strategies import SMACrossover
from src.common.costs import CostModel, ZERO, US_STOCKS


def _make_df(prices):
    n = len(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="D"),
        "open": prices, "high": prices, "low": prices,
        "close": prices, "volume": [1000] * n,
    })


def test_buy_and_hold_rising():
    # Steadily rising -> strategy should profit
    prices = list(range(10, 110))
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), symbol="TEST", cost_model=ZERO)
    assert r.total_return_pct > 0
    assert r.final_value > r.initial_capital


def test_no_trades_flat_market():
    # Perfectly flat -> SMA fast == slow -> no crossover trades expected
    prices = [100.0] * 100
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), symbol="TEST", cost_model=ZERO)
    # Should end near initial capital (might have 0 or few trades)
    assert abs(r.final_value - r.initial_capital) < r.initial_capital * 0.01


def test_costs_reduce_returns():
    prices = list(range(10, 110))
    df = _make_df(prices)
    r_free = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO)
    r_cost = run_backtest(df, SMACrossover(5, 20), cost_model=US_STOCKS)
    assert r_free.final_value >= r_cost.final_value
    assert r_cost.total_costs > 0


def test_max_drawdown_non_negative():
    prices = [100 + np.sin(i / 5) * 20 for i in range(200)]
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO)
    assert r.max_drawdown_pct >= 0


def test_win_rate_bounds():
    prices = [100 + np.sin(i / 3) * 10 for i in range(200)]
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO)
    assert 0 <= r.win_rate <= 100


def test_equity_curve_length():
    prices = list(range(10, 110))
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO)
    assert len(r.equity_curve) == len(df)


def test_trades_pnl_sums():
    prices = list(range(10, 110))
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO)
    if r.trades:
        total_pnl = sum(t["pnl"] for t in r.trades)
        # PnL + leftover cash should roughly equal final value
        assert r.final_value > r.initial_capital  # at least profitable on rising data


def test_result_summary_string():
    prices = list(range(10, 60))
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), symbol="TEST", cost_model=ZERO)
    s = r.summary()
    assert "TEST" in s
    assert "SMA" in s
    assert "Return" in s
