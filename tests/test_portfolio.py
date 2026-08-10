"""Tests for PortfolioSource abstraction — snapshot building and backend selection."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.common.clock import parse_dt
from src.common.portfolio import (
    BrokerPortfolioSource,
    MongoPortfolioSource,
    OrderInfo,
    PortfolioSnapshot,
    PositionInfo,
    build_portfolio_source,
)


def test_parse_dt_handles_z_suffix():
    utc = timezone.utc
    assert parse_dt("2026-05-31T10:00:00Z") == datetime(2026, 5, 31, 10, 0, 0, tzinfo=utc)
    assert parse_dt(None) is None
    assert parse_dt("garbage") is None
    assert parse_dt(datetime(2026, 1, 1)) == datetime(2026, 1, 1)


class TestMongoPortfolioSource:
    def test_load_builds_snapshot(self):
        pos_store = MagicMock()
        pos_store.get_positions_with_prices.return_value = {
            "AAPL": {"qty": 10, "entryPrice": 200.0, "entryTime": "2026-05-31T10:00:00Z"},
            "XOM": {"qty": 0, "entryPrice": 0.0},
        }
        order_store = MagicMock()
        order_store.find_recent.return_value = [
            {"symbol": "AAPL", "action": "buy", "shares": 10, "price": 200.0,
             "status": "filled", "order_id": "o1", "placed_at": "2026-05-31T09:00:00Z",
             "filled_at": "2026-05-31T09:00:05Z"},
        ]
        db = MagicMock()
        db.paper_account.find_one.return_value = {"_id": "paper_account", "cash": 1234.5}

        source = MongoPortfolioSource(position_store=pos_store, order_store=order_store, db=db, limit=5)
        snap = source._load()

        assert snap.source == "db"
        assert snap.cash == 1234.5
        assert snap.positions_by_symbol()["AAPL"].qty == 10
        assert snap.positions_by_symbol()["AAPL"].entry_price == 200.0
        assert len(snap.recent_orders) == 1
        assert snap.recent_orders[0].symbol == "AAPL"
        assert snap.recent_orders[0].action == "buy"
        assert snap.recent_orders[0].order_id == "o1"

    def test_cash_read_failure_does_not_raise(self):
        pos_store = MagicMock()
        pos_store.get_positions_with_prices.return_value = {}
        order_store = MagicMock()
        order_store.find_recent.return_value = []
        db = MagicMock()
        db.paper_account.find_one.side_effect = RuntimeError("mongo down")

        source = MongoPortfolioSource(position_store=pos_store, order_store=order_store, db=db)
        snap = source._load()

        assert snap.cash == 0.0
        assert snap.positions == []
        assert snap.recent_orders == []


class TestBrokerPortfolioSource:
    @pytest.mark.asyncio
    async def test_snapshot_from_broker(self):
        broker = MagicMock()
        broker.get_account_info = AsyncMock(return_value=MagicMock(cash=5000.0))
        broker.get_positions = AsyncMock(return_value={"AAPL": 10, "0700.HK": 100})
        broker.get_recent_orders = AsyncMock(return_value=[
            {"symbol": "0700.HK", "action": "sell", "qty": 100, "price": 380.0,
             "status": "filled", "placed_at": "2026-05-31T09:00:00Z"},
        ])

        snap = await BrokerPortfolioSource(broker).get_snapshot()

        assert snap.source == "broker"
        assert snap.cash == 5000.0
        assert snap.positions_by_symbol()["AAPL"].qty == 10
        assert len(snap.recent_orders) == 1
        assert snap.recent_orders[0].action == "sell"
        broker.get_recent_orders.assert_called_once_with(20)


class TestBuildPortfolioSource:
    def test_build_returns_mongo_by_default(self):
        source = build_portfolio_source("db")
        assert isinstance(source, MongoPortfolioSource)

    def test_build_broker_with_mock_factory(self, monkeypatch):
        fake_broker = MagicMock()
        monkeypatch.setattr("src.common.factories.build_broker", lambda: fake_broker)
        source = build_portfolio_source("broker")
        assert isinstance(source, BrokerPortfolioSource)
        assert source.broker is fake_broker


class TestBrokerOrderHistoryNotImplemented:
    @pytest.mark.asyncio
    async def test_base_broker_get_recent_orders_raises(self):
        """A broker without order history must fail loudly, not return []."""
        from src.live.brokers import Broker

        class StubBroker(Broker):
            async def execute(self, trade):
                return None

            async def get_positions(self):
                return {}

        broker = StubBroker()
        with pytest.raises(NotImplementedError, match="PORTFOLIO_SOURCE=broker"):
            await broker.get_recent_orders()


def test_positions_by_symbol_ignores_zero_qty_helper():
    snap = PortfolioSnapshot(
        source="db", as_of=datetime(2026, 1, 1),
        positions=[PositionInfo(symbol="AAPL", qty=5), PositionInfo(symbol="XOM", qty=0)],
    )
    assert snap.positions_by_symbol()["AAPL"].qty == 5
    assert "XOM" in snap.positions_by_symbol()
