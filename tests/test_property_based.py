"""Property-based tests for TradingLogic — SL/TP edge cases with Hypothesis."""
import pytest
from hypothesis import assume, given, strategies as st

from src.common.trading_logic import PositionState, TradingLogic

# Strategy for valid financial values
prices = st.floats(min_value=0.01, max_value=10000.0, allow_nan=False, allow_infinity=False)
small_pct = st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False)
shares = st.integers(min_value=1, max_value=100000)


class TestStopLossProperty:
    @given(sl_pct=small_pct, entry=prices, low=prices)
    def test_sl_never_above_entry(self, sl_pct, entry, low):
        assume(sl_pct > 0)
        logic = TradingLogic(stop_loss_pct=sl_pct)
        pos = PositionState("X", 10, entry)
        result = logic.check_stop_loss(pos, low)
        if result is not None:
            assert result <= entry

    @given(sl_pct=small_pct, entry=prices, low=prices)
    def test_sl_price_monotonic_with_entry(self, sl_pct, entry, low):
        """Higher entry price should produce higher (or equal) SL price at same loss pct."""
        assume(sl_pct > 0)
        logic = TradingLogic(stop_loss_pct=sl_pct)
        pos1 = PositionState("X", 10, entry)
        pos2 = PositionState("X", 10, entry * 2)
        r1 = logic.check_stop_loss(pos1, low)
        r2 = logic.check_stop_loss(pos2, low)
        # If both trigger, SL price scales with entry
        if r1 is not None and r2 is not None:
            assert r2 >= r1

    @given(sl_pct=small_pct, entry=prices, low=prices)
    def test_trailing_sl_never_below_fixed(self, sl_pct, entry, low):
        """Trailing SL should be >= fixed SL for same params."""
        assume(sl_pct > 0)
        logic_fixed = TradingLogic(stop_loss_pct=sl_pct, trailing_sl=False)
        logic_trail = TradingLogic(stop_loss_pct=sl_pct, trailing_sl=True)
        pos_fixed = PositionState("X", 10, entry)
        pos_trail = PositionState("X", 10, entry, peak_price=entry)
        r_fixed = logic_fixed.check_stop_loss(pos_fixed, low)
        r_trail = logic_trail.check_stop_loss(pos_trail, low)
        # Both None or both trigger with trail >= fixed (since peak >= entry)
        if r_fixed is not None and r_trail is not None:
            assert r_trail >= r_fixed


class TestTakeProfitProperty:
    @given(tp_pct=small_pct, entry=prices, high=prices)
    def test_tp_never_below_entry(self, tp_pct, entry, high):
        assume(tp_pct > 0)
        logic = TradingLogic(take_profit_pct=tp_pct)
        pos = PositionState("X", 10, entry)
        result = logic.check_take_profit(pos, high)
        if result is not None:
            assert result >= entry


class TestShouldBuyProperty:
    @given(
        sentiment=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        cash=prices,
        price=prices,
    )
    def test_never_negative_shares(self, sentiment, confidence, cash, price):
        assume(price > 0 and cash > 0)
        logic = TradingLogic(threshold=-1.0, min_confidence=0.0, max_allocation=1.0)
        shares = logic.should_buy(sentiment, confidence, "X", {}, cash, price)
        assert shares >= 0

    @given(
        sentiment=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        cash=prices,
        price=prices,
    )
    def test_market_value_never_exceeds_cash(self, sentiment, confidence, cash, price):
        assume(price > 0 and cash > 0)
        logic = TradingLogic(threshold=-1.0, min_confidence=0.0, max_allocation=1.0)
        shares = logic.should_buy(sentiment, confidence, "X", {}, cash, price)
        assert shares * price <= cash

    @given(
        sentiment=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
        cash=prices,
        price=prices,
        max_alloc=small_pct,
    )
    def test_respects_max_allocation(self, sentiment, confidence, cash, price, max_alloc):
        assume(price > 0 and cash > 0 and max_alloc > 0)
        logic = TradingLogic(threshold=-1.0, min_confidence=0.0, max_allocation=max_alloc)
        shares = logic.should_buy(sentiment, confidence, "X", {}, cash, price)
        assert shares * price <= cash * max_alloc
