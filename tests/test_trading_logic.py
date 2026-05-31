"""Unit tests for TradingLogic — should_buy, should_sell, SL/TP, position sizing."""
import pytest

from src.common.trading_logic import PositionState, TradingLogic


class TestShouldBuy:
    def test_low_confidence_returns_zero(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.5)
        assert logic.should_buy(0.8, 0.2, "AAPL", {}, 10000, 150) == 0

    def test_low_sentiment_returns_zero(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1)
        assert logic.should_buy(0.1, 0.9, "AAPL", {}, 10000, 150) == 0

    def test_already_holding_returns_zero(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1)
        positions = {"AAPL": "2026-01-01T00:00:00"}
        assert logic.should_buy(0.8, 0.9, "AAPL", positions, 10000, 150) == 0

    def test_basic_buy_with_max_allocation(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1, max_allocation=0.2)
        shares = logic.should_buy(0.5, 0.9, "AAPL", {}, 20000, 100)
        # alloc = 20000 * 0.2 = 4000 → 40 shares @ $100
        assert shares == 40

    def test_buy_capped_by_max_allocation(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1, max_allocation=0.1)
        shares = logic.should_buy(1.0, 0.9, "AAPL", {}, 20000, 100)
        # max_alloc 0.1 → alloc 2000 → 20 shares
        assert shares == 20

    def test_risk_per_trade_limits_allocation(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1,
                             max_allocation=1.0, risk_per_trade=0.02,
                             stop_loss_pct=0.05)
        shares = logic.should_buy(1.0, 0.9, "AAPL", {}, 20000, 100)
        # risk_alloc = (20000 * 0.02) / 0.05 = 8000 → 80 shares
        assert shares == 80

    def test_insufficient_cash_returns_zero(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1, max_allocation=1.0)
        shares = logic.should_buy(1.0, 0.9, "AAPL", {}, 100, 150)
        assert shares == 0

    def test_size_scales_when_max_allocation_is_zero(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1,
                             max_allocation=0.0)
        shares = logic.should_buy(0.5, 0.9, "AAPL", {}, 20000, 100)
        # size=0.5 → alloc = 20000 * 0.5 = 10000 → 100 shares
        assert shares == 100

    def test_no_scale_by_sentiment_when_max_alloc_zero(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1,
                             max_allocation=0.0, scale_by_sentiment=False)
        shares = logic.should_buy(0.1, 0.9, "AAPL", {}, 20000, 100)
        # size = 1.0 (no scaling) → alloc = 20000 → 200 shares
        # 200 * 100 = 20000, 20000 < 20000 is False → 0
        assert shares == 0

    def test_full_allocation(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1, max_allocation=1.0)
        shares = logic.should_buy(1.0, 0.9, "AAPL", {}, 20000, 100)
        # alloc 20000 → 200 shares, but 200*100=20000 not < 20000 → 0
        assert shares == 0


class TestShouldSellOnSentiment:
    def test_low_confidence_no_sell(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.5)
        assert logic.should_sell_on_sentiment(-0.8, 0.2, "AAPL", {"AAPL": "..."}) is False

    def test_not_holding_no_sell(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1)
        assert logic.should_sell_on_sentiment(-0.8, 0.9, "AAPL", {}) is False

    def test_bullish_sentiment_no_sell(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1)
        assert logic.should_sell_on_sentiment(0.8, 0.9, "AAPL", {"AAPL": "..."}) is False

    def test_bearish_while_holding_triggers_sell(self):
        logic = TradingLogic(threshold=0.3, min_confidence=0.1)
        assert logic.should_sell_on_sentiment(-0.5, 0.9, "AAPL", {"AAPL": "..."}) is True

    def test_sentiment_at_threshold_exact(self):
        logic = TradingLogic(threshold=0.5, min_confidence=0.1)
        assert logic.should_sell_on_sentiment(-0.5, 0.9, "AAPL", {"AAPL": "..."}) is True

    def test_sentiment_below_threshold_no_sell(self):
        logic = TradingLogic(threshold=0.5, min_confidence=0.1)
        assert logic.should_sell_on_sentiment(-0.4, 0.9, "AAPL", {"AAPL": "..."}) is False


class TestStopLoss:
    def test_no_sl_returns_none(self):
        logic = TradingLogic(stop_loss_pct=0)
        pos = PositionState("AAPL", 10, 100)
        assert logic.check_stop_loss(pos, 50) is None

    def test_below_sl_returns_price(self):
        logic = TradingLogic(stop_loss_pct=0.1)
        pos = PositionState("AAPL", 10, 100)
        price = logic.check_stop_loss(pos, 85)
        assert price == 90  # 100 * (1 - 0.1)

    def test_above_sl_returns_none(self):
        logic = TradingLogic(stop_loss_pct=0.1)
        pos = PositionState("AAPL", 10, 100)
        assert logic.check_stop_loss(pos, 95) is None

    def test_trailing_sl_uses_peak(self):
        logic = TradingLogic(stop_loss_pct=0.1, trailing_sl=True)
        pos = PositionState("AAPL", 10, 100)
        pos.peak_price = 120
        price = logic.check_stop_loss(pos, 105)
        assert price == 108  # 120 * (1 - 0.1)

    def test_trailing_sl_no_trigger_above_peak(self):
        logic = TradingLogic(stop_loss_pct=0.1, trailing_sl=True)
        pos = PositionState("AAPL", 10, 100)
        pos.peak_price = 120
        assert logic.check_stop_loss(pos, 115) is None


class TestTakeProfit:
    def test_no_tp_returns_none(self):
        logic = TradingLogic(take_profit_pct=0)
        pos = PositionState("AAPL", 10, 100)
        assert logic.check_take_profit(pos, 200) is None

    def test_above_tp_returns_price(self):
        logic = TradingLogic(take_profit_pct=0.1)
        pos = PositionState("AAPL", 10, 100)
        price = logic.check_take_profit(pos, 115)
        assert price == pytest.approx(110)  # 100 * (1 + 0.1)

    def test_below_tp_returns_none(self):
        logic = TradingLogic(take_profit_pct=0.1)
        pos = PositionState("AAPL", 10, 100)
        assert logic.check_take_profit(pos, 105) is None


class TestUpdatePeak:
    def test_updates_peak_when_trailing(self):
        logic = TradingLogic(trailing_sl=True)
        pos = PositionState("AAPL", 10, 100)
        logic.update_peak(pos, 150)
        assert pos.peak_price == 150

    def test_no_update_when_trailing_disabled(self):
        logic = TradingLogic(trailing_sl=False)
        pos = PositionState("AAPL", 10, 100)
        logic.update_peak(pos, 150)
        assert pos.peak_price == 100  # unchanged from entry

    def test_does_not_decrease_peak(self):
        logic = TradingLogic(trailing_sl=True)
        pos = PositionState("AAPL", 10, 100)
        pos.peak_price = 120
        logic.update_peak(pos, 80)
        assert pos.peak_price == 120  # peak only goes up


class TestPositionState:
    def test_default_peak_equals_entry(self):
        pos = PositionState("AAPL", 10, 100)
        assert pos.peak_price == 100

    def test_explicit_peak_preserved(self):
        pos = PositionState("AAPL", 10, 100, peak_price=150)
        assert pos.peak_price == 150
