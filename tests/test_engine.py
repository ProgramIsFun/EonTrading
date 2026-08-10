"""Tests for shared backtest helpers in src/backtest/engine.py."""
import pandas as pd
import pytest

from src.backtest.engine import check_position_exit
from src.common.costs import ZERO
from src.common.trading_logic import PositionState, TradingLogic


def _bar(open_=100.0, high=101.0, low=99.0, close=100.5):
    return pd.Series({"open": open_, "high": high, "low": low, "close": close})


def _state(entry=100.0, shares=100):
    return PositionState("TEST", shares, entry)


def test_no_exit_keeps_position():
    logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
    assert check_position_exit(logic, ZERO, _state(), _bar(), 0, 0, 0) is None


def test_stop_loss_priority_over_take_profit():
    logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
    action, price, headline = check_position_exit(logic, ZERO, _state(), _bar(high=112.0, low=94.0), 0, 0, 0)
    assert action == "sell (SL)"
    assert price == pytest.approx(95.0)
    assert headline == "Stop loss hit"


def test_take_profit_exit():
    logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
    action, price, headline = check_position_exit(logic, ZERO, _state(), _bar(high=112.0), 0, 0, 0)
    assert action == "sell (TP)"
    assert price == pytest.approx(110.0)
    assert headline == "Take profit hit"


def test_max_hold_exit_at_bar_open():
    logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
    action, price, headline = check_position_exit(logic, ZERO, _state(), _bar(open_=99.5), 5, 0, 3)
    assert action == "sell (expire)"
    assert price == pytest.approx(99.5)
    assert headline == "Max hold reached"


def test_max_hold_disabled_when_zero():
    logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10)
    assert check_position_exit(logic, ZERO, _state(), _bar(), 5, 0, 0) is None


def test_trailing_stop_loss_uses_peak():
    logic = TradingLogic(stop_loss_pct=0.05, take_profit_pct=0.10, trailing_sl=True)
    state = _state()
    state.peak_price = 110.0
    action, price, _ = check_position_exit(logic, ZERO, state, _bar(low=100.0), 0, 0, 0)
    assert action == "sell (SL)"
    assert price == 104.5
