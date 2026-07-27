"""Tests for backtest endpoint response format — catches regressions during result formatting refactor."""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from httpx import ASGITransport, AsyncClient

from src.backtest.engine import BacktestResult, Trade
from src.backtest import SentimentTrade


@pytest.fixture
def mock_mongo():
    with patch("src.api.server.get_db") as m:
        mock_db = MagicMock()
        mock_db["heartbeats"].find.return_value = []
        mock_db["positions"].find.return_value = []
        m.return_value = mock_db
        yield m


@pytest.fixture
def app(mock_mongo):
    from src.api.server import app
    return app


def _make_backtest_result():
    return BacktestResult(
        strategy="SMA Crossover",
        symbol="AAPL",
        initial_capital=10000,
        final_value=12500.0,
        total_return_pct=25.0,
        annual_return_pct=25.0,
        max_drawdown_pct=5.0,
        total_trades=10,
        win_rate=60.0,
        sharpe_ratio=1.5,
        total_costs=50.0,
        trades=[
            Trade("AAPL", "long", 150.0, 160.0, 10, 100.0, "2025-01-01", "2025-01-15"),
            Trade("AAPL", "long", 160.0, 155.0, 10, -50.0, "2025-01-15", "2025-02-01"),
        ],
        equity_curve=pd.Series([10000, 10500, 11000, 12500]),
    )


def _make_portfolio_result():
    result = MagicMock()
    result.initial_capital = 70000
    result.final_value = 75000.0
    result.total_return_pct = 7.14
    result.max_drawdown_pct = 3.2
    result.total_trades = 5
    result.win_rate = 60.0
    result.equity_curve = pd.Series([70000, 71000, 73000, 75000])
    result.trades = [
        SentimentTrade("AAPL", "buy", "2025-01-01", 150.0, 0.8, "AAPL beats earnings"),
        SentimentTrade("AAPL", "sell", "2025-01-15", 160.0, -0.6, "AAPL misses guidance"),
    ]
    return result


# --- /api/price-backtest ---

SHARED_FIELDS = {"initial_capital", "final_value", "total_return_pct", "max_drawdown_pct",
                 "total_trades", "win_rate", "equity_curve", "trades"}


class TestPriceBacktestResponse:
    @pytest.mark.asyncio
    async def test_returns_all_shared_fields(self, app):
        result = _make_backtest_result()
        mock_df = pd.DataFrame({
            "open": [150.0], "high": [155.0], "low": [148.0], "close": [152.0],
            "timestamp": pd.to_datetime(["2025-01-01"]),
        })

        with patch("yfinance.download", return_value=mock_df), \
             patch("src.backtest.run_backtest", return_value=result), \
             patch("src.data.ingest.yfinance_ingest.normalize_yfinance_df", return_value=mock_df):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/price-backtest?symbol=AAPL&start=2025-01-01&end=2025-01-02")

        assert resp.status_code == 200
        data = resp.json()
        for field in SHARED_FIELDS:
            assert field in data, f"Missing shared field: {field}"

    @pytest.mark.asyncio
    async def test_returns_price_backtest_specific_fields(self, app):
        result = _make_backtest_result()
        mock_df = pd.DataFrame({
            "open": [150.0], "high": [155.0], "low": [148.0], "close": [152.0],
            "timestamp": pd.to_datetime(["2025-01-01"]),
        })

        with patch("yfinance.download", return_value=mock_df), \
             patch("src.backtest.run_backtest", return_value=result), \
             patch("src.data.ingest.yfinance_ingest.normalize_yfinance_df", return_value=mock_df):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/price-backtest?symbol=AAPL&start=2025-01-01&end=2025-01-02")

        data = resp.json()
        assert data["strategy"] == "SMA Crossover"
        assert data["symbol"] == "AAPL"
        assert "annual_return_pct" in data
        assert "sharpe_ratio" in data

    @pytest.mark.asyncio
    async def test_values_are_rounded(self, app):
        result = _make_backtest_result()
        mock_df = pd.DataFrame({
            "open": [150.0], "high": [155.0], "low": [148.0], "close": [152.0],
            "timestamp": pd.to_datetime(["2025-01-01"]),
        })

        with patch("yfinance.download", return_value=mock_df), \
             patch("src.backtest.run_backtest", return_value=result), \
             patch("src.data.ingest.yfinance_ingest.normalize_yfinance_df", return_value=mock_df):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/price-backtest?symbol=AAPL&start=2025-01-01&end=2025-01-02")

        data = resp.json()
        assert data["final_value"] == 12500.0
        assert data["total_return_pct"] == 25.0
        assert data["win_rate"] == 60.0
        assert isinstance(data["equity_curve"], list)

    @pytest.mark.asyncio
    async def test_trades_have_expected_fields(self, app):
        result = _make_backtest_result()
        mock_df = pd.DataFrame({
            "open": [150.0], "high": [155.0], "low": [148.0], "close": [152.0],
            "timestamp": pd.to_datetime(["2025-01-01"]),
        })

        with patch("yfinance.download", return_value=mock_df), \
             patch("src.backtest.run_backtest", return_value=result), \
             patch("src.data.ingest.yfinance_ingest.normalize_yfinance_df", return_value=mock_df):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/price-backtest?symbol=AAPL&start=2025-01-01&end=2025-01-02")

        trades = resp.json()["trades"]
        assert len(trades) == 2
        trade_fields = {"symbol", "side", "entry_price", "exit_price", "shares", "pnl", "entry_date", "exit_date"}
        for t in trades:
            assert trade_fields.issubset(t.keys()), f"Missing trade fields: {trade_fields - t.keys()}"

    @pytest.mark.asyncio
    async def test_empty_data_returns_error(self, app):
        empty_df = pd.DataFrame()

        with patch("yfinance.download", return_value=empty_df):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/price-backtest?symbol=INVALID&start=2025-01-01&end=2025-01-02")

        data = resp.json()
        assert "error" in data


# --- /api/backtest ---

class TestPortfolioBacktestResponse:
    @pytest.mark.asyncio
    async def test_returns_all_shared_fields(self, app):
        result = _make_portfolio_result()

        with patch("src.api.server.run_portfolio_backtest", return_value=result):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/backtest")

        assert resp.status_code == 200
        data = resp.json()
        for field in SHARED_FIELDS:
            assert field in data, f"Missing shared field: {field}"

    @pytest.mark.asyncio
    async def test_values_are_correct(self, app):
        result = _make_portfolio_result()

        with patch("src.api.server.run_portfolio_backtest", return_value=result):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/backtest")

        data = resp.json()
        assert data["initial_capital"] == 70000
        assert data["final_value"] == 75000.0
        assert data["total_return_pct"] == 7.14
        assert data["total_trades"] == 5
        assert data["win_rate"] == 60.0

    @pytest.mark.asyncio
    async def test_trades_have_sentiment_fields(self, app):
        result = _make_portfolio_result()

        with patch("src.api.server.run_portfolio_backtest", return_value=result):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/backtest")

        trades = resp.json()["trades"]
        assert len(trades) == 2
        trade_fields = {"symbol", "action", "date", "price", "shares", "sentiment", "pnl", "headline"}
        for t in trades:
            assert trade_fields.issubset(t.keys()), f"Missing trade fields: {trade_fields - t.keys()}"

    @pytest.mark.asyncio
    async def test_equity_curve_is_list(self, app):
        result = _make_portfolio_result()

        with patch("src.api.server.run_portfolio_backtest", return_value=result):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/backtest")

        assert isinstance(resp.json()["equity_curve"], list)
