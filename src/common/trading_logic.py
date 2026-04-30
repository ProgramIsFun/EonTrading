"""Shared trading logic used by both backtest and live trader."""
from dataclasses import dataclass


@dataclass
class PositionState:
    symbol: str
    shares: int
    entry_price: float
    peak_price: float = 0.0

    def __post_init__(self):
        if self.peak_price == 0:
            self.peak_price = self.entry_price


class TradingLogic:
    """Core trading decisions — shared between backtest and live."""

    def __init__(
        self,
        threshold: float = 0.5,
        min_confidence: float = 0.15,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.10,
        trailing_sl: bool = False,
        max_allocation: float = 0.2,
        risk_per_trade: float = 0.0,
        scale_by_sentiment: bool = True,
    ):
        self.threshold = threshold
        self.min_confidence = min_confidence
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.trailing_sl = trailing_sl
        self.max_allocation = max_allocation
        self.risk_per_trade = risk_per_trade
        self.scale_by_sentiment = scale_by_sentiment

    def should_buy(self, sentiment: float, confidence: float, symbol: str, positions: dict, cash: float, price: float) -> int:
        """Returns number of shares to buy, or 0 if no trade."""
        if confidence < self.min_confidence:
            return 0
        if sentiment < self.threshold:
            return 0
        if symbol in positions:
            return 0

        size = min(abs(sentiment), 1.0) if self.scale_by_sentiment else 1.0
        alloc = cash * self.max_allocation if self.max_allocation > 0 else cash * size
        if self.risk_per_trade > 0 and self.stop_loss_pct > 0:
            risk_alloc = (cash * self.risk_per_trade) / self.stop_loss_pct
            alloc = min(alloc, risk_alloc)

        shares = int(alloc / price)
        return shares if shares > 0 and shares * price < cash else 0

    def should_sell_on_sentiment(self, sentiment: float, confidence: float, symbol: str, positions: dict) -> bool:
        """Check if bearish sentiment triggers a sell."""
        if confidence < self.min_confidence:
            return False
        return sentiment <= -self.threshold and symbol in positions

    def check_stop_loss(self, pos: PositionState, low: float) -> float | None:
        """Returns sell price if SL hit, None otherwise."""
        if self.stop_loss_pct <= 0:
            return None
        ref = pos.peak_price if self.trailing_sl else pos.entry_price
        sl_price = ref * (1 - self.stop_loss_pct)
        if low <= sl_price:
            return sl_price
        return None

    def check_take_profit(self, pos: PositionState, high: float) -> float | None:
        """Returns sell price if TP hit, None otherwise."""
        if self.take_profit_pct <= 0:
            return None
        tp_price = pos.entry_price * (1 + self.take_profit_pct)
        if high >= tp_price:
            return tp_price
        return None

    def update_peak(self, pos: PositionState, high: float):
        """Update trailing SL peak price."""
        if self.trailing_sl and high > pos.peak_price:
            pos.peak_price = high
