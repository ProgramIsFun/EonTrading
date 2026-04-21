import clickhouse_connect
import pandas as pd
from datetime import datetime
from .base_storage import StorageBackend


class ClickHouseStorage(StorageBackend):
    def __init__(self, host: str = "192.168.0.38", port: int = 8123, database: str = "eontrading"):
        self.client = clickhouse_connect.get_client(host=host, port=port, database=database)

    def insert_ohlcv(self, df: pd.DataFrame, symbol: str, exchange: str, interval: str):
        if df.empty:
            return
        rows = [
            [symbol, exchange, interval,
             row["timestamp"], row["open"], row["high"], row["low"], row["close"], row["volume"]]
            for _, row in df.iterrows()
        ]
        self.client.insert("ohlcv",
            rows,
            column_names=["symbol", "exchange", "interval", "timestamp", "open", "high", "low", "close", "volume"]
        )

    def query_ohlcv(self, symbol: str, interval: str, start: datetime, end: datetime) -> pd.DataFrame:
        result = self.client.query_df(
            "SELECT timestamp, open, high, low, close, volume FROM ohlcv "
            "WHERE symbol = {symbol:String} AND interval = {interval:String} "
            "AND timestamp >= {start:DateTime64(3)} AND timestamp <= {end:DateTime64(3)} "
            "ORDER BY timestamp",
            parameters={"symbol": symbol, "interval": interval, "start": start, "end": end}
        )
        return result

    def get_latest_timestamp(self, symbol: str, interval: str) -> datetime | None:
        result = self.client.query(
            "SELECT max(timestamp) FROM ohlcv "
            "WHERE symbol = {symbol:String} AND interval = {interval:String}",
            parameters={"symbol": symbol, "interval": interval}
        )
        val = result.result_rows[0][0]
        return val if val and val.year > 1970 else None
