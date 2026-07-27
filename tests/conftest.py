"""Shared test fixtures.

All tests mock MongoDB. If complex queries or aggregations are added, consider a real test DB.
"""
import logging
import pytest

from src.common.event_bus import LocalEventBus
from tests.helpers import MockBroker

TEST_DB_NAME = "EonTradingDB_test"


@pytest.fixture(autouse=True)
def _isolate_test_logging():
    """Prevent test log output from polluting production log files."""
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    root.handlers = []
    yield
    root.handlers = saved_handlers


@pytest.fixture
def event_bus():
    return LocalEventBus()


@pytest.fixture
def mock_broker():
    return MockBroker()


@pytest.fixture
def test_db():
    """Real MongoDB database fixture for integration tests.

    Uses a separate test database (EonTradingDB_test) that gets dropped
    after each test to ensure isolation. Requires a running MongoDB instance.
    """
    from src.data.utils.db_helper import get_mongo_client

    client = get_mongo_client()
    db = client[TEST_DB_NAME]
    yield db
    client.drop_database(TEST_DB_NAME)
