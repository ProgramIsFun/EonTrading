import pandas as pd
import numpy as np
from src.strategies import SMACrossover, RSIMeanReversion


def _make_df(prices):
    """Helper: create minimal OHLCV df from a list of close prices."""
    n = len(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2020-01-01", periods=n, freq="D"),
        "open": prices, "high": prices, "low": prices,
        "close": prices, "volume": [1000] * n,
    })


def test_sma_crossover_signal_values():
    s = SMACrossover(fast=3, slow=5)
    df = _make_df([10, 11, 12, 13, 14, 15, 16, 17, 18, 19])
    signals = s.generate_signals(df)
    assert set(signals.dropna().unique()).issubset({-1, 0, 1})


def test_sma_crossover_bullish():
    # Steadily rising prices -> fast > slow -> buy signal
    prices = list(range(1, 61))
    df = _make_df(prices)
    s = SMACrossover(fast=5, slow=20)
    signals = s.generate_signals(df)
    # After warmup, should be mostly buy signals
    late_signals = signals.iloc[25:]
    assert (late_signals == 1).all()


def test_sma_crossover_bearish():
    # Steadily falling prices -> fast < slow -> sell signal
    prices = list(range(60, 0, -1))
    df = _make_df(prices)
    s = SMACrossover(fast=5, slow=20)
    signals = s.generate_signals(df)
    late_signals = signals.iloc[25:]
    assert (late_signals == -1).all()


def test_sma_name():
    assert SMACrossover(10, 30).name() == "SMA(10,30)"


def test_rsi_oversold_generates_buy():
    # Sharp drop then flat -> RSI should go oversold -> buy
    prices = [100] * 20 + [100 - i * 3 for i in range(1, 16)]
    df = _make_df(prices)
    s = RSIMeanReversion(period=14, oversold=30, overbought=70)
    signals = s.generate_signals(df)
    assert 1 in signals.values


def test_rsi_overbought_generates_sell():
    # Sharp rise -> RSI should go overbought -> sell
    prices = [50] * 20 + [50 + i * 3 for i in range(1, 16)]
    df = _make_df(prices)
    s = RSIMeanReversion(period=14, oversold=30, overbought=70)
    signals = s.generate_signals(df)
    assert -1 in signals.values


def test_rsi_name():
    assert RSIMeanReversion().name() == "RSI(14,30,70)"
