"""Base strategy interface."""
from abc import ABC, abstractmethod
import pandas as pd


class Strategy(ABC):
    """
    A strategy receives OHLCV data and produces signals.
    Signals: 1 = buy, -1 = sell, 0 = hold.
    """

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        Given a DataFrame with columns [timestamp, open, high, low, close, volume],
        return a Series of signals (1, -1, 0) aligned to the same index.
        """
        pass
