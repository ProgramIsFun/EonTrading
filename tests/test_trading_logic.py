"""Unit tests for TradingLogic — should_buy, should_sell, SL/TP, position sizing."""
import pytest

from src.common.trading_logic import PositionState, TradingLogic


class TestShouldBuy:
    @pytest.mark.parametrize("desc,kwargs,sentiment,confidence,positions,cash,price,expected", [
        ("low confidence",  dict(threshold=0.3, min_confidence=0.5), 0.8, 0.2, {}, 10000, 150, 0),
        ("low sentiment",   dict(threshold=0.3, min_confidence=0.1), 0.1, 0.9, {}, 10000, 150, 0),
        ("already holding", dict(threshold=0.3, min_confidence=0.1), 0.8, 0.9, {"AAPL": "..."}, 10000, 150, 0),
        ("max alloc 20%",   dict(threshold=0.3, min_confidence=0.1, max_allocation=0.2), 0.5, 0.9, {}, 20000, 100, 40),
        ("max alloc 10%",   dict(threshold=0.3, min_confidence=0.1, max_allocation=0.1), 1.0, 0.9, {}, 20000, 100, 20),
        ("risk per trade",  dict(threshold=0.3, min_confidence=0.1, max_allocation=1.0,
                                 risk_per_trade=0.02, stop_loss_pct=0.05), 1.0, 0.9, {}, 20000, 100, 80),
        ("insufficient cash", dict(threshold=0.3, min_confidence=0.1, max_allocation=1.0), 1.0, 0.9, {}, 100, 150, 0),
        ("max alloc zero scales", dict(threshold=0.3, min_confidence=0.1, max_allocation=0.0), 0.5, 0.9, {}, 20000, 100, 100),
        ("no scale by sentiment", dict(threshold=0.3, min_confidence=0.1, max_allocation=0.0,
                                       scale_by_sentiment=False), 0.1, 0.9, {}, 20000, 100, 0),
        ("full allocation capped", dict(threshold=0.3, min_confidence=0.1, max_allocation=1.0), 1.0, 0.9, {}, 20000, 100, 0),
    ])
    def test_should_buy(self, desc, kwargs, sentiment, confidence, positions, cash, price, expected):
        logic = TradingLogic(**kwargs)
        assert logic.should_buy(sentiment, confidence, "AAPL", positions, cash, price) == expected, desc


class TestShouldSellOnSentiment:
    @pytest.mark.parametrize("desc,sentiment,confidence,positions,expected", [
        ("low confidence no sell",     -0.8, 0.05, {"AAPL": "..."}, False),
        ("not holding no sell",        -0.8, 0.9, {},               False),
        ("bullish no sell",            0.8,  0.9, {"AAPL": "..."}, False),
        ("bearish while holding sell", -0.5, 0.9, {"AAPL": "..."}, True),
        ("at threshold exactly",       -0.5, 0.9, {"AAPL": "..."}, True),
        ("below threshold no sell",    -0.4, 0.9, {"AAPL": "..."}, False),
    ])
    def test_should_sell_on_sentiment(self, desc, sentiment, confidence, positions, expected):
        logic = TradingLogic(threshold=0.5, min_confidence=0.1)
        assert logic.should_sell_on_sentiment(sentiment, confidence, "AAPL", positions) is expected


class TestStopLoss:
    @pytest.mark.parametrize("desc,sl_pct,entry,low,trailing,peak,expected", [
        ("no sl",           0,    100, 50,  False, None,  None),
        ("below sl",        0.1,  100, 85,  False, None,  90.0),
        ("above sl none",   0.1,  100, 95,  False, None,  None),
        ("trailing uses peak", 0.1, 100, 105, True, 120,  108.0),
        ("trailing above peak none", 0.1, 100, 115, True, 120,  None),
    ])
    def test_check_stop_loss(self, desc, sl_pct, entry, low, trailing, peak, expected):
        logic = TradingLogic(stop_loss_pct=sl_pct, trailing_sl=trailing)
        pos = PositionState("AAPL", 10, entry, peak_price=peak or entry)
        result = logic.check_stop_loss(pos, low)
        if expected is None:
            assert result is None
        else:
            assert result == expected


class TestTakeProfit:
    @pytest.mark.parametrize("desc,tp_pct,entry,high,expected", [
        ("no tp",        0,   100, 200,  None),
        ("above tp",     0.1, 100, 115,  110.0),
        ("below tp",     0.1, 100, 105,  None),
    ])
    def test_check_take_profit(self, desc, tp_pct, entry, high, expected):
        logic = TradingLogic(take_profit_pct=tp_pct)
        pos = PositionState("AAPL", 10, entry)
        result = logic.check_take_profit(pos, high)
        if expected is None:
            assert result is None
        else:
            assert result == pytest.approx(expected)


class TestUpdatePeak:
    @pytest.mark.parametrize("desc,trailing,start_peak,new_price,expected", [
        ("updates when trailing",   True,  100, 150, 150),
        ("no update no trailing",   False, 100, 150, 100),
        ("does not decrease peak",  True,  120, 80,  120),
    ])
    def test_update_peak(self, desc, trailing, start_peak, new_price, expected):
        logic = TradingLogic(trailing_sl=trailing)
        pos = PositionState("AAPL", 10, 100, peak_price=start_peak)
        logic.update_peak(pos, new_price)
        assert pos.peak_price == expected


class TestPositionState:
    def test_default_peak_equals_entry(self):
        pos = PositionState("AAPL", 10, 100)
        assert pos.peak_price == 100

    def test_explicit_peak_preserved(self):
        pos = PositionState("AAPL", 10, 100, peak_price=150)
        assert pos.peak_price == 150
