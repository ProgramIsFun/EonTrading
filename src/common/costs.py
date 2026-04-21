"""Transaction cost models."""
from dataclasses import dataclass


@dataclass
class CostModel:
    commission: float = 0.0        # flat $ per trade
    commission_pct: float = 0.0    # % of trade value
    slippage_pct: float = 0.0005   # 0.05% default
    stamp_duty_pct: float = 0.0    # HK: 0.1% on sells

    def buy_cost(self, price: float, shares: int) -> float:
        """Return total cost of buying (added to price)."""
        value = price * shares
        return self.commission + value * (self.commission_pct + self.slippage_pct)

    def sell_cost(self, price: float, shares: int) -> float:
        """Return total cost of selling (subtracted from proceeds)."""
        value = price * shares
        return self.commission + value * (self.commission_pct + self.slippage_pct + self.stamp_duty_pct)

    def effective_buy_price(self, price: float) -> float:
        return price * (1 + self.slippage_pct + self.commission_pct)

    def effective_sell_price(self, price: float) -> float:
        return price * (1 - self.slippage_pct - self.commission_pct - self.stamp_duty_pct)


# Presets
US_STOCKS = CostModel(commission=0.99, slippage_pct=0.0005)
HK_STOCKS = CostModel(commission=0.0, slippage_pct=0.001, stamp_duty_pct=0.001)
CRYPTO = CostModel(commission_pct=0.001, slippage_pct=0.0005)
ZERO = CostModel(slippage_pct=0.0)  # for testing without costs
