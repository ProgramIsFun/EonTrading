"""Shared test fixtures.

All tests mock MongoDB. If complex queries or aggregations are added, consider a real test DB.
"""
import logging
import pytest

from src.common.event_bus import LocalEventBus
from tests.helpers import MockBroker


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
