"""Shared test fixtures.

All tests mock MongoDB. If complex queries or aggregations are added, consider a real test DB.
"""
import pytest

from src.common.event_bus import LocalEventBus
from tests.helpers import MockBroker


@pytest.fixture
def event_bus():
    return LocalEventBus()


@pytest.fixture
def mock_broker():
    return MockBroker()
