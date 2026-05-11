# src\eontrading_datagrabber\providers\base_provider.py
from abc import ABC, abstractmethod


class MarketDataProviderError(Exception):
    """Custom exception for market data provider errors."""
    pass


class MarketDataProvider(ABC):
    @abstractmethod
    def fetchMarketDataFromSymbol(self, symbol: str) -> dict:
        pass

    @abstractmethod
    def fetchMarketDataFromSymbols(self, symbols: list[str]) -> dict:
        """Fetch market data for multiple symbols. Returns a dictionary keyed by symbol."""
        pass

    @abstractmethod
    def getAvailableSymbols(self) -> list[str]:
        """
        Return a list of available symbols provided by this data provider.
        """
        pass

    @abstractmethod
    def getProviderName(self) -> str:
        """Return the name of the data provider."""
        pass
