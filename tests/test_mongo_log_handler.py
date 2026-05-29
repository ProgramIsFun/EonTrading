"""Tests for MongoLogHandler and opencode LLM integration."""
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

# Mock MongoClient before importing news_trader (module-level get_mongo_client())
mock_client = MagicMock()
mock_db = MagicMock()
mock_client.__getitem__.return_value = mock_db
with patch("src.data.utils.db_helper.get_mongo_client", return_value=mock_client):
    from src.common.log_handler import MongoBatchHandler as MongoLogHandler
    import src.live.news_trader  # triggers handler registration on root logger

from src.strategies.sentiment import LLMSentimentAnalyzer


class TestMongoLogHandler:
    def test_handler_added_to_root_logger(self):
        """MongoLogHandler is added to root logger when news_trader imports."""
        root = logging.getLogger()
        found = any(isinstance(h, MongoLogHandler) for h in root.handlers)
        assert found, "MongoLogHandler should be registered on root logger"

    def test_emit_swallows_exceptions(self):
        """Handler should not crash on emit failures."""
        handler = MongoLogHandler()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname=__file__, lineno=10, msg="test", args=(), exc_info=None,
        )
        handler.emit(record)

    def test_emit_queues_record(self):
        """Handler queues the record for batch flush."""
        handler = MongoLogHandler()

        record = logging.LogRecord(
            name="test", level=logging.WARNING,
            pathname=__file__, lineno=20, msg="test warning", args=(), exc_info=None,
        )
        handler.emit(record)

        # Record should be in the queue (_not_ flushed yet)
        queued = handler._queue.get_nowait()
        assert queued.getMessage() == "test warning"


class TestLLMSentimentAnalyzerOpencode:
    def test_opencode_key_sets_correct_defaults(self):
        """OPENCODE_API_KEY env var configures analyzer for opencode Zen."""
        os.environ["OPENCODE_API_KEY"] = "sk-test-key"
        try:
            a = LLMSentimentAnalyzer()
            assert a.api_key == "sk-test-key"
            assert "opencode.ai" in a.base_url
            assert a.model in ("big-pickle",)
        finally:
            del os.environ["OPENCODE_API_KEY"]

    def test_opencode_key_no_azure(self):
        """Opencode config should not set azure flag."""
        os.environ["OPENCODE_API_KEY"] = "sk-test-key"
        try:
            a = LLMSentimentAnalyzer()
            assert not a._is_azure
        finally:
            del os.environ["OPENCODE_API_KEY"]

    def test_openai_key_fallback_when_no_opencode(self):
        """Without OPENCODE_API_KEY, falls back to OpenAI defaults."""
        os.environ.pop("OPENCODE_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ.pop("OPENAI_MODEL", None)
        a = LLMSentimentAnalyzer()
        assert a.api_key is None
        assert "api.openai.com" in a.base_url
        assert a.model == "gpt-4o-mini"

    def test_opencode_custom_model(self):
        """OPENCODE_MODEL env var overrides default big-pickle."""
        os.environ["OPENCODE_API_KEY"] = "sk-test"
        os.environ["OPENCODE_MODEL"] = "deepseek-v4-flash-free"
        try:
            a = LLMSentimentAnalyzer()
            assert a.model == "deepseek-v4-flash-free"
        finally:
            del os.environ["OPENCODE_API_KEY"]
            del os.environ["OPENCODE_MODEL"]

    def test_constructor_explicit_wins_over_env(self):
        """Explicit constructor args override OPENCODE_API_KEY env."""
        os.environ["OPENCODE_API_KEY"] = "sk-env-key"
        try:
            a = LLMSentimentAnalyzer(api_key="sk-explicit", base_url="https://custom.url/v1", model="custom-model")
            assert a.api_key == "sk-explicit"
            assert a.base_url == "https://custom.url/v1"
            assert a.model == "custom-model"
        finally:
            del os.environ["OPENCODE_API_KEY"]

    def test_opencode_uses_chat_completions_endpoint(self):
        """Verify _call_llm constructs the right URL for opencode."""
        os.environ["OPENCODE_API_KEY"] = "sk-test"
        try:
            a = LLMSentimentAnalyzer()
            with patch("requests.post") as mock_post:
                mock_post.return_value = MagicMock(status_code=200, json=lambda: {"choices": [{"message": {"content": '{"symbols":[],"sentiment":0,"confidence":0}'}}]})
                a._call_llm("test prompt")
                called_url = mock_post.call_args[0][0]
                assert called_url.endswith("/chat/completions")
                assert "opencode.ai" in called_url
        finally:
            del os.environ["OPENCODE_API_KEY"]
