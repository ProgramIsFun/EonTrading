"""Integration tests using a real MongoDB instance.

These tests require a running MongoDB server on localhost:27017.
Run with: pytest -m integration -v
"""
from datetime import datetime, timedelta

import pytest

from src.common.position_store import MongoPositionStore
from src.common.order_store import MongoOrderStore
from src.common.clock import utcnow
from src.live.brokers.paper import PaperBroker

pytestmark = pytest.mark.integration


class TestMongoPositionStore:
    def test_open_and_close(self, test_db):
        store = MongoPositionStore(db=test_db, collection="test_positions")
        now = utcnow()

        store.open_position("AAPL", now, entry_price=150.0, qty=10)
        positions = store.get_positions_with_prices()
        assert "AAPL" in positions
        assert positions["AAPL"]["qty"] == 10
        assert positions["AAPL"]["entryPrice"] == 150.0

        store.close_position("AAPL")
        assert store.get_positions() == {}

    def test_averaging_merges_qty_and_price(self, test_db):
        store = MongoPositionStore(db=test_db, collection="test_positions")
        now = utcnow()

        store.open_position("TSLA", now, entry_price=200.0, qty=10)
        store.open_position("TSLA", now, entry_price=250.0, qty=10)

        positions = store.get_positions_with_prices()
        assert positions["TSLA"]["qty"] == 20
        assert positions["TSLA"]["entryPrice"] == pytest.approx(225.0)

    def test_update_peak(self, test_db):
        store = MongoPositionStore(db=test_db, collection="test_positions")
        now = utcnow()

        store.open_position("MSFT", now, entry_price=300.0, qty=5)
        store.update_peak("MSFT", 320.0)

        positions = store.get_positions_with_prices()
        assert positions["MSFT"]["peakPrice"] == 320.0

    def test_set_positions_syncs(self, test_db):
        store = MongoPositionStore(db=test_db, collection="test_positions")
        now = utcnow()

        store.set_positions({"AAPL": now, "GOOG": now})
        assert set(store.get_positions().keys()) == {"AAPL", "GOOG"}

        store.set_positions({"AAPL": now})
        assert set(store.get_positions().keys()) == {"AAPL"}

    def test_list_all(self, test_db):
        store = MongoPositionStore(db=test_db, collection="test_positions")
        now = utcnow()

        store.open_position("AAPL", now, entry_price=150.0, qty=10)
        store.open_position("GOOG", now, entry_price=2800.0, qty=2)

        all_pos = store.list_all()
        symbols = {p["symbol"] for p in all_pos}
        assert symbols == {"AAPL", "GOOG"}


class TestMongoOrderStore:
    def test_insert_and_find_by_order_id(self, test_db):
        store = MongoOrderStore(db=test_db, collection="test_orders")
        doc = {"order_id": "ord-123", "status": "pending", "symbol": "AAPL"}
        store.insert(doc)

        found = store.find_by_order_id("ord-123")
        assert found is not None
        assert found["symbol"] == "AAPL"

    def test_find_pending(self, test_db):
        store = MongoOrderStore(db=test_db, collection="test_orders")
        now = utcnow()
        store.insert({
            "order_id": "ord-pending",
            "status": "pending",
            "next_check_at": now - timedelta(seconds=1),
        })
        store.insert({
            "order_id": "ord-future",
            "status": "pending",
            "next_check_at": now + timedelta(hours=1),
        })

        pending = store.find_pending(now)
        ids = [o["order_id"] for o in pending]
        assert "ord-pending" in ids
        assert "ord-future" not in ids

    def test_mark_filled(self, test_db):
        store = MongoOrderStore(db=test_db, collection="test_orders")
        doc = {"_id": "ord-456", "order_id": "ord-456", "status": "pending"}
        store.insert(doc)

        store.mark_filled("ord-456", utcnow())
        found = store.find_by_order_id("ord-456")
        assert found["status"] == "filled"

    def test_mark_failed(self, test_db):
        store = MongoOrderStore(db=test_db, collection="test_orders")
        doc = {"_id": "ord-789", "order_id": "ord-789", "status": "pending"}
        store.insert(doc)

        store.mark_failed("ord-789", "insufficient funds")
        found = store.find_by_order_id("ord-789")
        assert found["status"] == "failed"
        assert found["error"] == "insufficient funds"

    def test_update_retry(self, test_db):
        store = MongoOrderStore(db=test_db, collection="test_orders")
        now = utcnow()
        doc = {"_id": "ord-retry", "order_id": "ord-retry", "status": "pending", "retry_count": 0}
        store.insert(doc)

        next_check = now + timedelta(minutes=5)
        store.update_retry("ord-retry", next_check, now, 1)

        found = store.find_by_order_id("ord-retry")
        assert found["retry_count"] == 1
        assert abs((found["next_check_at"] - next_check).total_seconds()) < 1


class TestPaperBrokerCashPersistence:
    def test_cash_persists_across_instances(self, test_db):
        # Override the DB for PaperBroker
        from src.data.utils import db_helper
        original_get_db = db_helper.get_db
        db_helper.get_db = lambda: test_db
        try:
            broker1 = PaperBroker(initial_cash=100000, persist_cash=True)
            assert broker1._cash == 100000

            # Simulate spending cash
            broker1._cash = 50000
            broker1._save_cash()

            # Create new instance — should load persisted cash
            broker2 = PaperBroker(initial_cash=100000, persist_cash=True)
            assert broker2._cash == 50000
        finally:
            db_helper.get_db = original_get_db

    def test_cash_not_persisted_when_disabled(self, test_db):
        from src.data.utils import db_helper
        original_get_db = db_helper.get_db
        db_helper.get_db = lambda: test_db
        try:
            broker = PaperBroker(initial_cash=100000, persist_cash=False)
            broker._cash = 75000
            broker._save_cash()

            # New instance should use default cash
            broker2 = PaperBroker(initial_cash=100000, persist_cash=False)
            assert broker2._cash == 100000
        finally:
            db_helper.get_db = original_get_db
