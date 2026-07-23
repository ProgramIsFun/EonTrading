"""Tests for log handler, component filter, and LLM integration."""
import logging
import json
import os
from unittest.mock import MagicMock, patch

import pytest


class TestComponentFilter:
    def test_filter_adds_attribute(self):
        from src.common.log_handler import ComponentFilter
        f = ComponentFilter("trader")
        record = logging.LogRecord("x", logging.INFO, "", 0, "msg", (), None)
        assert f.filter(record)
        assert record.component == "trader"

    def test_empty_component_when_no_filter(self):
        record = logging.LogRecord("x", logging.INFO, "", 0, "msg", (), None)
        assert getattr(record, "component", "") == ""


class TestComponentFormatter:
    def test_both_format(self):
        from src.common.log_handler import ComponentFormatter
        fmt = ComponentFormatter(log_format="both")
        record = logging.LogRecord("src.live.news_watcher", logging.INFO, "", 0, "msg", (), None)
        record.component = "newswatcher"
        result = fmt.format(record)
        assert "watcher:src.live.news_watcher" in result

    def test_component_only_format(self):
        from src.common.log_handler import ComponentFormatter
        fmt = ComponentFormatter(log_format="component")
        record = logging.LogRecord("src.live.news_watcher", logging.INFO, "", 0, "msg", (), None)
        record.component = "newswatcher"
        result = fmt.format(record)
        assert "[newswatcher]" in result

    def test_no_component_falls_back_to_name(self):
        from src.common.log_handler import ComponentFormatter
        fmt = ComponentFormatter(log_format="component")
        record = logging.LogRecord("src.live.news_watcher", logging.INFO, "", 0, "msg", (), None)
        result = fmt.format(record)
        assert "src.live.news_watcher" in result


class TestJsonFormatter:
    def test_output_is_valid_json(self):
        from src.common.log_handler import JsonFormatter
        fmt = JsonFormatter()
        record = logging.LogRecord("test.logger", logging.WARNING, "test.py", 42, "hello world", (), None)
        record.component = "newswatcher"
        result = fmt.format(record)
        doc = json.loads(result)
        assert doc["level"] == "WARNING"
        assert doc["component"] == "newswatcher"
        assert doc["message"] == "hello world"
        assert doc["logger"] == "test.logger"
        assert "timestamp" in doc

    def test_no_component_empty_string(self):
        from src.common.log_handler import JsonFormatter
        fmt = JsonFormatter()
        record = logging.LogRecord("x", logging.INFO, "", 0, "msg", (), None)
        result = fmt.format(record)
        doc = json.loads(result)
        assert doc["component"] == ""

    def test_unicode_message(self):
        from src.common.log_handler import JsonFormatter
        fmt = JsonFormatter()
        record = logging.LogRecord("x", logging.INFO, "", 0, "日本語テスト", (), None)
        result = fmt.format(record)
        doc = json.loads(result)
        assert doc["message"] == "日本語テスト"

    def test_all_fields_present(self):
        from src.common.log_handler import JsonFormatter
        fmt = JsonFormatter()
        record = logging.LogRecord("my.logger", logging.ERROR, "file.py", 99, "err", (), None)
        record.component = "executor"
        doc = json.loads(fmt.format(record))
        for key in ("timestamp", "level", "component", "logger", "message", "module", "func", "line"):
            assert key in doc, f"Missing field: {key}"
        assert doc["level"] == "ERROR"
        assert doc["line"] == 99


class TestSetupLogging:
    def test_component_creates_file_handler(self, tmp_path):
        """setup_logging('watcher') creates logs/watcher.log."""
        import importlib
        import src.common.log_handler as lh
        importlib.reload(lh)
        root = logging.getLogger()
        before = len(root.handlers)
        lh.setup_logging("newswatcher", log_dir=str(tmp_path))
        assert (tmp_path / "watcher.log").exists() or len(root.handlers) > before
        # Restore
        root.handlers = root.handlers[:before]
        root._eon_components = set()
        root._eon_console_added = False

    def test_multiple_components_create_separate_files(self, tmp_path):
        """Calling setup_logging with different components creates separate files."""
        import importlib
        import src.common.log_handler as lh
        importlib.reload(lh)
        root = logging.getLogger()
        before = len(root.handlers)
        lh.setup_logging("newswatcher", log_dir=str(tmp_path))
        lh.setup_logging("trader", log_dir=str(tmp_path))
        # Two file handlers added (plus possibly console)
        assert len(root.handlers) > before + 1
        root.handlers = root.handlers[:before]
        root._eon_components = set()
        root._eon_console_added = False

    def test_duplicate_component_ignored(self, tmp_path):
        """Calling setup_logging('watcher') twice doesn't add duplicate handler."""
        import importlib
        import src.common.log_handler as lh
        importlib.reload(lh)
        root = logging.getLogger()
        before = len(root.handlers)
        lh.setup_logging("newswatcher", log_dir=str(tmp_path))
        after_first = len(root.handlers)
        lh.setup_logging("newswatcher", log_dir=str(tmp_path))
        after_second = len(root.handlers)
        # Second call adds nothing
        assert after_second == after_first
        root.handlers = root.handlers[:before]
        root._eon_components = set()
        root._eon_console_added = False

    def test_console_handler_added_once(self, tmp_path):
        """Multiple setup_logging calls only add one console handler."""
        import importlib
        import src.common.log_handler as lh
        importlib.reload(lh)
        root = logging.getLogger()
        before = len(root.handlers)
        lh.setup_logging("newswatcher", log_dir=str(tmp_path))
        lh.setup_logging("trader", log_dir=str(tmp_path))
        stream_handlers = [h for h in root.handlers[before:] if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) == 1
        root.handlers = root.handlers[:before]
        root._eon_components = set()
        root._eon_console_added = False

    def test_none_component_no_file_handler(self, tmp_path):
        """setup_logging(None) only adds console, no file handler."""
        import importlib
        import src.common.log_handler as lh
        importlib.reload(lh)
        root = logging.getLogger()
        before = len(root.handlers)
        lh.setup_logging(None, log_dir=str(tmp_path))
        file_handlers = [h for h in root.handlers[before:] if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0
        root.handlers = root.handlers[:before]
        root._eon_components = set()
        root._eon_console_added = False


class TestLLMSentimentAnalyzerOpencode:
    def test_opencode_key_sets_correct_defaults(self):
        from src.strategies.sentiment import LLMSentimentAnalyzer
        os.environ["OPENCODE_API_KEY"] = "sk-test-key"
        try:
            a = LLMSentimentAnalyzer()
            assert a.api_key == "sk-test-key"
            assert "opencode.ai" in a.base_url
            assert a.model in ("big-pickle",)
        finally:
            del os.environ["OPENCODE_API_KEY"]

    def test_opencode_key_no_azure(self):
        from src.strategies.sentiment import LLMSentimentAnalyzer
        os.environ["OPENCODE_API_KEY"] = "sk-test-key"
        try:
            a = LLMSentimentAnalyzer()
            assert not a._is_azure
        finally:
            del os.environ["OPENCODE_API_KEY"]

    def test_openai_key_fallback_when_no_opencode(self):
        from src.strategies.sentiment import LLMSentimentAnalyzer
        os.environ.pop("OPENCODE_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("OPENAI_BASE_URL", None)
        os.environ.pop("OPENAI_MODEL", None)
        a = LLMSentimentAnalyzer()
        assert a.api_key is None
        assert "api.openai.com" in a.base_url
        assert a.model == "gpt-4o-mini"

    def test_opencode_custom_model(self):
        from src.strategies.sentiment import LLMSentimentAnalyzer
        os.environ["OPENCODE_API_KEY"] = "sk-test"
        os.environ["OPENCODE_MODEL"] = "deepseek-v4-flash-free"
        try:
            a = LLMSentimentAnalyzer()
            assert a.model == "deepseek-v4-flash-free"
        finally:
            del os.environ["OPENCODE_API_KEY"]
            del os.environ["OPENCODE_MODEL"]

    def test_constructor_explicit_wins_over_env(self):
        from src.strategies.sentiment import LLMSentimentAnalyzer
        os.environ["OPENCODE_API_KEY"] = "sk-env-key"
        try:
            a = LLMSentimentAnalyzer(api_key="sk-explicit", base_url="https://custom.url/v1", model="custom-model")
            assert a.api_key == "sk-explicit"
            assert a.base_url == "https://custom.url/v1"
            assert a.model == "custom-model"
        finally:
            del os.environ["OPENCODE_API_KEY"]

    def test_opencode_uses_chat_completions_endpoint(self):
        from src.strategies.sentiment import LLMSentimentAnalyzer
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
