"""Base strategy interface."""
from abc import ABC, abstractmethod
from dataclasses import dataclass

import pandas as pd


@dataclass
class Signal:
    action: int  # 1=buy, -1=sell, 0=hold
    size: float = 1.0  # fraction of capital (0.0 to 1.0)
    stop_loss: float = 0.0  # 0=use engine default
    take_profit: float = 0.0  # 0=use engine default

    @staticmethod
    def from_value(val) -> "Signal":
        """Convert simple int/float or Signal to Signal."""
        if isinstance(val, Signal):
            return val
        return Signal(action=int(val))


class Strategy(ABC):
    """
    A strategy receives OHLCV data and produces signals.

    generate_signals() can return either:
      - pd.Series of int (1, -1, 0) — simple mode, backward compatible
      - pd.Series of Signal objects — rich mode, per-trade control
    """

    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        pass
