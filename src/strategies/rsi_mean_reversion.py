"""Buy when RSI < oversold, sell when RSI > overbought."""
import pandas as pd
from .base_strategy import Strategy


class RSIMeanReversion(Strategy):
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
