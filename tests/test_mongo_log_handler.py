"""Tests for MongoLogHandler and opencode LLM integration."""
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

mock_client = MagicMock()
mock_db = MagicMock()
mock_client.__getitem__.return_value = mock_db
with patch("src.data.utils.db_helper.get_mongo_client", return_value=mock_client):
    from src.live.news_trader import MongoLogHandler

from src.strategies.sentiment import LLMSentimentAnalyzer


class TestMongoLogHandler:
    def test_handler_added_to_root_logger(self):
        root = logging.getLogger()
        found = any(isinstance(h, MongoLogHandler) for h in root.handlers)
        assert found

    def test_emit_swallows_exceptions(self):
        handler = MongoLogHandler()
        record = logging.LogRecord(
            name="test", level=logging.INFO,
            pathname=__file__, lineno=10, msg="test", args=(), exc_info=None,
        )
        handler.emit(record)

    def test_emit_calls_insert_one(self):
        mock_col = MagicMock()
        handler = MongoLogHandler()
        handler._col = mock_col

        record = logging.LogRecord(
            name="test", level=logging.WARNING,
            pathname=__file__, lineno=20, msg="test warning", args=(), exc_info=None,
        )
        handler.emit(record)

        mock_col.insert_one.assert_called_once()
        doc = mock_col.insert_one.call_args[0][0]
        assert doc["level"] == "WARNING"
        assert doc["message"] == "test warning"


class TestLLMSentimentAnalyzerOpencode:
    def test_opencode_key_sets_correct_defaults(self):
        os.environ["OPENCODE_API_KEY"] = "sk-test-key"
        try:
            a = LLMSentimentAnalyzer()
            assert a.api_key == "sk-test-key"
            assert "opencode.ai" in a.base_url
            assert a.model in ("big-pickle",)
        finally:
            del os.environ["OPENCODE_API_KEY"]

    def test_opencode_key_no_azure(self):
        os.environ["OPENCODE_API_KEY"] = "sk-test-key"
        try:
            a = LLMSentimentAnalyzer()
            assert not a._is_azure
        finally:
            del os.environ["OPENCODE_API_KEY"]

    def test_openai_key_fallback_when_no_opencode(self):
        os.environ.pop("OPENCODE_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ.pop("OPENAI_MODEL", None)
        a = LLMSentimentAnalyzer()
        assert a.api_key is None
        assert "api.openai.com" in a.base_url
        assert a.model == "gpt-4o-mini"

    def test_opencode_custom_model(self):
        os.environ["OPENCODE_API_KEY"] = "sk-test"
        os.environ["OPENCODE_MODEL"] = "deepseek-v4-flash-free"
        try:
            a = LLMSentimentAnalyzer()
            assert a.model == "deepseek-v4-flash-free"
        finally:
            del os.environ["OPENCODE_API_KEY"]
            del os.environ["OPENCODE_MODEL"]

    def test_constructor_explicit_wins_over_env(self):
        os.environ["OPENCODE_API_KEY"] = "sk-env-key"
        try:
            a = LLMSentimentAnalyzer(api_key="sk-explicit", base_url="https://custom.url/v1", model="custom-model")
            assert a.api_key == "sk-explicit"
            assert a.base_url == "https://custom.url/v1"
            assert a.model == "custom-model"
        finally:
            del os.environ["OPENCODE_API_KEY"]

    @pytest.mark.asyncio
    async def test_opencode_uses_chat_completions_endpoint(self):
        os.environ["OPENCODE_API_KEY"] = "sk-test"
        try:
            a = LLMSentimentAnalyzer()
            mock_resp = MagicMock(status_code=200, json=lambda: {"choices": [{"message": {"content": '{"symbols":[],"sentiment":0,"confidence":0}'}}]})
            with patch("httpx.AsyncClient.post", return_value=mock_resp):
                await a._call_llm("test prompt")
                called_url = mock_resp.post.call_args[0][0]
                assert called_url.endswith("/chat/completions")
                assert "opencode.ai" in called_url
        finally:
            del os.environ["OPENCODE_API_KEY"]
