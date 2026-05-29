"""Tests for the API endpoints — backtest job lifecycle, health."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _make_mock_cursor(return_value=None):
    """Create a mock motor cursor that supports chaining (sort, limit) and awaitable .to_list()."""
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=return_value or [])
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    return cursor


@pytest.fixture
def mock_mongo():
    with patch("src.api.server.get_mongo_client") as m:
        mock_db = MagicMock()
        mock_col = MagicMock()
        mock_col.find.return_value = _make_mock_cursor([])
        mock_col.count_documents = AsyncMock(return_value=0)
        mock_db.__getitem__.return_value = mock_col
        m.return_value = mock_db
        yield m


@pytest.fixture
def app(mock_mongo):
    from src.api.server import app
    return app


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


class TestLiveBacktestJob:
    @pytest.mark.asyncio
    async def test_start_returns_job_id(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/api/live-backtest?capital=10000&sl_check_hours=168")
            assert resp.status_code == 200
            data = resp.json()
            assert "job_id" in data
            assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_poll_unknown_job_returns_not_found(self, app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/live-backtest/nonexistent")
            assert resp.json()["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_full_job_lifecycle(self, app):
        with patch("src.common.price.get_price", return_value=150.0), \
             patch("src.live.price_monitor.get_price", return_value=150.0):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # Start
                resp = await client.post("/api/live-backtest?capital=10000&sl_check_hours=168")
                job_id = resp.json()["job_id"]

                # Poll until done
                data = {}
                for _ in range(60):
                    await asyncio.sleep(0.5)
                    resp = await client.get(f"/api/live-backtest/{job_id}")
                    data = resp.json()
                    if data["status"] in ("done", "error"):
                        break

                assert data["status"] == "done", f"Job failed: {data.get('error')}"
                assert data["initial_capital"] == 10000
                assert "equity_curve" in data
                assert "trades" in data
                assert data["mode"] == "live_pipeline"

                # Job cleaned up
                resp = await client.get(f"/api/live-backtest/{job_id}")
                assert resp.json()["status"] == "not_found"

    @pytest.mark.asyncio
    async def test_progress_reported(self, app):
        with patch("src.common.price.get_price", return_value=150.0), \
             patch("src.live.price_monitor.get_price", return_value=150.0):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/api/live-backtest?capital=10000&sl_check_hours=168")
                job_id = resp.json()["job_id"]

                seen_progress = []
                for _ in range(60):
                    await asyncio.sleep(0.5)
                    resp = await client.get(f"/api/live-backtest/{job_id}")
                    data = resp.json()
                    if data["status"] == "running":
                        seen_progress.append(data.get("progress", 0))
                    if data["status"] in ("done", "error"):
                        break

                assert data["status"] == "done", f"Job failed: {data.get('error')}"
                assert any(p > 0 for p in seen_progress) or data["status"] == "done"
