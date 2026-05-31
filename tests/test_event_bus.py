"""Unit tests for LocalEventBus — publish/subscribe, error handling, lifecycle."""
import asyncio
from unittest.mock import patch

import pytest

from src.common.event_bus import LocalEventBus


@pytest.fixture
def raw_bus():
    return LocalEventBus()


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_single_subscriber_receives_message(self, raw_bus):
        bus = raw_bus
        await bus.start()
        received = []
        async def handler(msg):
            received.append(msg)
        await bus.subscribe("test", handler)
        await bus.publish("test", {"key": "val"})
        await asyncio.sleep(0.05)
        assert received == [{"key": "val"}]
        await bus.stop()

    @pytest.mark.asyncio
    async def test_multiple_subscribers_all_receive(self, raw_bus):
        bus = raw_bus
        await bus.start()
        r1, r2 = [], []
        async def h1(msg): r1.append(msg)
        async def h2(msg): r2.append(msg)
        await bus.subscribe("ch", h1)
        await bus.subscribe("ch", h2)
        await bus.publish("ch", {"n": 1})
        await asyncio.sleep(0.05)
        assert r1 == [{"n": 1}]
        assert r2 == [{"n": 1}]
        await bus.stop()

    @pytest.mark.asyncio
    async def test_other_channels_not_affected(self, raw_bus):
        bus = raw_bus
        await bus.start()
        received = []
        async def handler(msg): received.append(msg)
        await bus.subscribe("ch1", handler)
        await bus.publish("ch2", {"x": 1})
        await asyncio.sleep(0.05)
        assert received == []
        await bus.stop()


class TestPublish:
    @pytest.mark.asyncio
    async def test_no_subscribers_logs_warning(self, raw_bus):
        bus = raw_bus
        await bus.start()
        with patch("src.common.event_bus.logger.warning") as mock_warn:
            await bus.publish("empty", {"x": 1})
            mock_warn.assert_called_once()
            assert "No subscribers" in mock_warn.call_args[0][0]
        await bus.stop()


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_handler_exception_does_not_crash_bus(self, raw_bus):
        bus = raw_bus
        await bus.start()
        received = []
        async def bad_handler(msg): raise ValueError("boom")
        async def good_handler(msg): received.append(msg)

        await bus.subscribe("ch", bad_handler)
        await bus.subscribe("ch", good_handler)

        with patch("src.common.event_bus.logger.error") as mock_err:
            await bus.publish("ch", {"key": "val"})
            await asyncio.sleep(0.05)

        assert received == [{"key": "val"}]
        assert mock_err.called
        await bus.stop()


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop_clears_subscribers(self):
        bus = LocalEventBus()
        async def h(msg): pass
        await bus.subscribe("ch", h)
        await bus.stop()
        assert bus._subscribers == {}

    @pytest.mark.asyncio
    async def test_stop_idempotent(self):
        bus = LocalEventBus()
        await bus.stop()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        bus = LocalEventBus()
        await bus.start()
        await bus.start()
        await bus.stop()

    @pytest.mark.asyncio
    async def test_subscribe_after_stop_works(self, raw_bus):
        bus = raw_bus
        await bus.stop()
        received = []
        async def handler(msg): received.append(msg)
        await bus.subscribe("ch", handler)
        await bus.publish("ch", {"ok": True})
        await asyncio.sleep(0.05)
        assert received == [{"ok": True}]
