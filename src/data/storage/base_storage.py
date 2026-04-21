from abc import ABC, abstractmethod
from datetime import datetime
import pandas as pd


class StorageBackend(ABC):
    @abstractmethod
    def insert_ohlcv(self, df: pd.DataFrame, symbol: str, exchange: str, interval: str):
        """Insert OHLCV dataframe. Expects columns: timestamp, open, high, low, close, volume."""
        pass

    @abstractmethod
    def query_ohlcv(self, symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Query OHLCV data for a symbol and interval within a time range."""
        pass

    @abstractmethod
    def get_latest_timestamp(self, symbol: str, interval: str) -> datetime | None:
        """Get the most recent timestamp for a symbol/interval. Used to resume ingestion."""
        pass
