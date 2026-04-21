"""Simple Moving Average crossover. Buy when fast SMA crosses above slow SMA."""
import pandas as pd
from .base_strategy import Strategy


class SMACrossover(Strategy):
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
