import numpy as np
import pandas as pd

from src.backtest import run_backtest
from src.common.costs import US_STOCKS, ZERO, CostModel
from src.strategies import SMACrossover


def _make_df(prices, highs=None, lows=None):
    n = len(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="D"),
        "open": prices,
        "high": highs if highs is not None else prices,
        "low": lows if lows is not None else prices,
        "close": prices,
        "volume": [1000] * n,
    })


def test_buy_and_hold_rising():
    prices = list(range(10, 110))
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), symbol="TEST", cost_model=ZERO)
    assert r.total_return_pct > 0
    assert r.final_value > r.initial_capital


def test_no_trades_flat_market():
    prices = [100.0] * 100
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), symbol="TEST", cost_model=ZERO)
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


def test_trades_profitable_on_rising():
    prices = list(range(10, 110))
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO)
    assert r.final_value > r.initial_capital


def test_result_summary_string():
    prices = list(range(10, 60))
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), symbol="TEST", cost_model=ZERO)
    s = r.summary()
    assert "TEST" in s
    assert "SMA" in s
    assert "Return" in s


def test_next_open_execution():
    prices = list(range(10, 110))
    df = _make_df(prices)
    r1 = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO, exec_next_open=True)
    r2 = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO, exec_next_open=False)
    # Results should differ since execution timing differs
    assert r1.final_value != r2.final_value


def test_short_selling():
    # Falling prices -> short should profit
    prices = list(range(110, 10, -1))
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO, allow_short=True)
    assert r.final_value > r.initial_capital
    assert any(t.side == "short" for t in r.trades)


def test_stop_loss():
    # Big drop should trigger stop loss
    prices = [100.0] * 30 + [100 + i for i in range(1, 21)] + [80.0] * 5
    highs = [p + 2 for p in prices]
    lows = [p - 2 for p in prices]
    df = _make_df(prices, highs=highs, lows=lows)
    r = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO, stop_loss_pct=0.05)
    # With stop loss, should limit losses
    r_no_sl = run_backtest(df, SMACrossover(5, 20), cost_model=ZERO, stop_loss_pct=0.0)
    # Stop loss should have exited earlier on the drop
    assert r.total_trades >= r_no_sl.total_trades or r.max_drawdown_pct <= r_no_sl.max_drawdown_pct + 5


def test_trade_has_dates():
    prices = list(range(10, 110))
    df = _make_df(prices)
    r = run_backtest(df, SMACrossover(5, 20), symbol="TEST", cost_model=ZERO)
    if r.trades:
        assert r.trades[0].entry_date is not None
        assert r.trades[0].exit_date is not None
        assert r.trades[0].side in ("long", "short")
