"""Example strategies."""
import pandas as pd
from .base_strategy import Strategy


class SMACrossover(Strategy):
    """Simple Moving Average crossover. Buy when fast SMA crosses above slow SMA."""

    def __init__(self, fast: int = 20, slow: int = 50):
        self.fast = fast
        self.slow = slow

    def name(self) -> str:
        return f"SMA({self.fast},{self.slow})"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast_ma = df["close"].rolling(self.fast).mean()
        slow_ma = df["close"].rolling(self.slow).mean()
        signal = pd.Series(0, index=df.index)
        signal[fast_ma > slow_ma] = 1
        signal[fast_ma <= slow_ma] = -1
        return signal


class RSIMeanReversion(Strategy):
    """Buy when RSI < oversold, sell when RSI > overbought."""

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def name(self) -> str:
        return f"RSI({self.period},{self.oversold},{self.overbought})"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        delta = df["close"].diff()
        gain = delta.clip(lower=0).rolling(self.period).mean()
        loss = (-delta.clip(upper=0)).rolling(self.period).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))

        signal = pd.Series(0, index=df.index)
        signal[rsi < self.oversold] = 1
        signal[rsi > self.overbought] = -1
        return signal
