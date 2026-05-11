import pytest

from src.common.costs import US_STOCKS, ZERO, CostModel


def test_zero_cost():
    c = ZERO
    assert c.buy_cost(100, 10) == 0
    assert c.sell_cost(100, 10) == 0
    assert c.effective_buy_price(100) == 100
    assert c.effective_sell_price(100) == 100


def test_us_stocks_commission():
    c = US_STOCKS  # $0.99 commission + 0.05% slippage
    cost = c.buy_cost(100, 10)  # $1000 trade
    assert cost == pytest.approx(0.99 + 1000 * 0.0005, abs=0.01)


def test_effective_prices():
    c = CostModel(slippage_pct=0.001, commission_pct=0.001)
    assert c.effective_buy_price(100) == pytest.approx(100.2)
    assert c.effective_sell_price(100) == pytest.approx(99.8)


def test_stamp_duty_on_sell_only():
    c = CostModel(stamp_duty_pct=0.001, slippage_pct=0.0)
    assert c.buy_cost(100, 10) == 0  # no stamp on buy
    assert c.sell_cost(100, 10) == pytest.approx(1000 * 0.001)


def test_round_trip_cost():
    c = CostModel(commission=1.0, slippage_pct=0.001)
    buy = c.buy_cost(100, 10)
    sell = c.sell_cost(100, 10)
    # Round trip should cost 2x commission + 2x slippage
    assert buy + sell == pytest.approx(2.0 + 2000 * 0.001)
