# src\eontrading_datagrabber\providers\yfinance_provider.py
from typing import Any, List, Optional, Union

import pandas as pd
import yfinance as yf
from eontrading_datagrabber.providers.base_provider import MarketDataProvider, MarketDataProviderError


class YFinanceProvider(MarketDataProvider):
    def fetchMarketDataFromSymbol(self, symbol: str) -> dict:
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d")
            if data.empty:
                raise MarketDataProviderError(f"No data found for symbol '{symbol}'")
            return {
                "symbol": symbol,
                "price": float(data['Close'].iloc[-1]),
                "volume": int(data['Volume'].iloc[-1]),
                "date": str(data.index[-1].date()),
            }
        except Exception as e:
            raise MarketDataProviderError(f"Error fetching data for '{symbol}': {str(e)}")

    def yf_download_wrapper(
        tickers: Union[str, List[str]],  # List of tickers to download (str or list)
        start: Optional[str] = None,  # Download start date (YYYY-MM-DD or datetime); default is 99 years ago
        end: Optional[str] = None,  # Download end date (YYYY-MM-DD or datetime); default is now
        actions: bool = False,  # Download dividend + stock splits data; default is False
        threads: bool = True,  # Number of threads to use for mass downloading; default is True
        ignore_tz: Optional[bool] = None,  # Ignore timezone adjustments; default depends on interval
        group_by: str = 'column',  # Group by 'ticker' or 'column'; default is 'column'
        auto_adjust: Optional[bool] = None,  # Adjust all OHLC automatically; default is True
        back_adjust: bool = False,  # Back-adjust prices for splits/dividends; default is False
        repair: bool = False,  # Detect currency unit mixups and attempt repair; default is False
        keepna: bool = False,  # Keep NaN rows returned by Yahoo; default is False
        progress: bool = True,  # Show download progress bar; default is True
        period: Optional[str] = None,  # Valid periods (e.g. '1mo', '1y', etc.); default is None
        interval: str = '1d',  # Valid intervals (e.g. '1d', '5m', etc.); default is '1d'
        prepost: bool = False,  # Include pre and post market data; default is False
        proxy=None,  # Proxy server to use; default is _SENTINEL_
        rounding: bool = False,  # Round values to 2 decimal places? Default is False
        timeout: int = 10,  # Timeout for response in seconds; default is 10
        session: Any = None,  # Requests session object; default is None
        multi_level_index: bool = True  # Always return MultiIndex DataFrame; default is True
    ) -> Union[pd.DataFrame, None]:
        '''ways to return error ?https://github.com/ProgramIsFun/EonTrading-DataGrabber/issues/1 '''
        '''if start,end,period are None, default to 1mo period'''
        '''Only 8 days worth of 1m granularity data are allowed to be fetched per request.'''
        '''if tickers too much, it will reach rate limit and fail'''
        '''if period 1d, interval 1d, might get no data for low liquidity stocks'''
        '''period 5d, interval 1d, 1000 tickers is ok'''
        '''
        success:

             yahoo_symbols[:1500], # str, list
             start=None,
             end=None,
             actions=False,
             threads=True,
             ignore_tz=None,
             group_by='ticker',
             auto_adjust=None,
             back_adjust=False,
             repair=False,
             keepna=False,
             progress=True,
             period='5d', # Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max Default: 1mo Either Use period parameter or use start and end
             interval='1d', # Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo Intraday data cannot extend last 60 days
             prepost=True,
             #  proxy=<object object>,
             rounding=False,
             timeout=10,
             session=None,
             multi_level_index=True

             if change to 8000 tickers, will get rate limit


        success:  thread disabled

             yahoo_symbols[:3000], # str, list
             start=None,
             end=None,
             actions=False,
             threads=False,
             ignore_tz=None,
             group_by='ticker',
             auto_adjust=None,
             back_adjust=False,
             repair=False,
             keepna=False,
             progress=True,
             period='5d', # Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max Default: 1mo Either Use period parameter or use start and end
             interval='1d', # Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo Intraday data cannot extend last 60 days
             prepost=True,
             #  proxy=<object object>,
             rounding=False,
             timeout=10,
             session=None,
             multi_level_index=True


        '''
        return yf.download(
            tickers=tickers,
            start=start,
            end=end,
            actions=actions,
            threads=threads,
            ignore_tz=ignore_tz,
            group_by=group_by,
            auto_adjust=auto_adjust,
            back_adjust=back_adjust,
            repair=repair,
            keepna=keepna,
            progress=progress,
            period=period,
            interval=interval,
            prepost=prepost,
            proxy=proxy,
            rounding=rounding,
            timeout=timeout,
            session=session,
            multi_level_index=multi_level_index
        )

    def fetchMarketDataFromSymbols(self, symbols: list[str]) -> dict:
        mode="foreach"
        match mode:
            case "batch":
                try:
                    # use download method to get data for multiple tickers
                    results = yf.download(tickers=symbols, period="1d", group_by='ticker', threads=True)
                except Exception as e:
                    raise MarketDataProviderError(f"Error fetching batch data: {str(e)}")
            case "foreach":
                results = {}
                for symbol in symbols:
                    try:
                        results[symbol] = self.fetchMarketDataFromSymbol(symbol)
                    except MarketDataProviderError as e:
                        results[symbol] = {"error": str(e)}
                return results

    def get_latest_price_by_fast_info(symbol):
        # single symbol only
        import yfinance as yf
        ticker = yf.Ticker(symbol)    # Tickers does not support fast_info
        return ticker.fast_info['last_price']

    def getAvailableSymbols(self) -> list[str]:
        mode="2"
        match mode:
            case "1":
                # ref https://github.com/DenisLitvin/yahoo_finance_stock_symbols_scraper
                raise NotImplementedError("Mode 1 is not implemented.")
            case "2":
                # read from db and we do format change
                from eontrading_datagrabber.utils.db_helper import getSymbolsList
                symbolsList = getSymbolsList()
                def hkex_to_yahoo(stock_code):
                    return f"{int(stock_code):04d}.HK"
                yahoo_symbols = [hkex_to_yahoo(item['stock_code']) for item in symbolsList if 'stock_code' in item]
                return yahoo_symbols
            case _:
                raise ValueError("Invalid mode selected.")

        raise NotImplementedError("getAvailableSymbols is not implemented for YFinanceProvider.")



    def getProviderName(self) -> str:
        return "YFinance"
