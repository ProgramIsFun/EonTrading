"""Tests for LogCollector — file tailing, MongoDB writing, callback broadcasting."""
import json
import logging
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.common.log_collector import LogCollector


class TestLogCollector:
    def test_tails_new_json_lines(self, tmp_path):
        """Collector picks up new JSON lines written to a log file."""
        log_file = tmp_path / "watcher.log"
        received = []

        collector = LogCollector(
            log_dir=str(tmp_path),
            get_mongo_fn=None,
            on_log=lambda doc: received.append(doc),
        )
        collector.start()

        # Write a JSON log line
        doc = {"timestamp": "2025-01-01T00:00:00Z", "level": "INFO", "component": "watcher",
               "logger": "test", "message": "hello", "module": "m", "func": "f", "line": 1}
        log_file.write_text(json.dumps(doc) + "\n")

        time.sleep(1.5)
        collector.stop()

        assert len(received) >= 1
        assert received[-1]["message"] == "hello"
        assert received[-1]["component"] == "watcher"

    def test_tails_plain_text_lines(self, tmp_path):
        """Collector handles plain text lines (non-JSON)."""
        log_file = tmp_path / "trader.log"
        received = []

        collector = LogCollector(
            log_dir=str(tmp_path),
            on_log=lambda doc: received.append(doc),
        )
        collector.start()

        log_file.write_text("plain text log line\n")

        time.sleep(1.5)
        collector.stop()

        assert len(received) >= 1
        assert received[-1]["message"] == "plain text log line"
        assert received[-1]["component"] == "trader"

    def test_writes_to_mongodb(self, tmp_path):
        """Collector batches and writes to MongoDB."""
        mock_col = MagicMock()
        log_file = tmp_path / "analyzer.log"

        collector = LogCollector(
            log_dir=str(tmp_path),
            get_mongo_fn=lambda: mock_col,
        )
        collector.start()

        doc = {"timestamp": "2025-01-01T00:00:00Z", "level": "INFO", "component": "analyzer",
               "logger": "test", "message": "test", "module": "m", "func": "f", "line": 1}
        log_file.write_text(json.dumps(doc) + "\n")

        time.sleep(1.5)
        collector.stop()

        assert mock_col.insert_many.called

    def test_multiple_files(self, tmp_path):
        """Collector watches multiple component files simultaneously."""
        received = []

        collector = LogCollector(
            log_dir=str(tmp_path),
            on_log=lambda doc: received.append(doc),
        )
        collector.start()

        (tmp_path / "watcher.log").write_text('{"component":"watcher","message":"w1","level":"INFO","timestamp":"","logger":"","module":"","func":"","line":0}\n')
        (tmp_path / "trader.log").write_text('{"component":"trader","message":"t1","level":"INFO","timestamp":"","logger":"","module":"","func":"","line":0}\n')

        time.sleep(1.5)
        collector.stop()

        messages = [d["message"] for d in received]
        assert "w1" in messages
        assert "t1" in messages

    def test_log_count(self, tmp_path):
        """log_count tracks total processed lines."""
        log_file = tmp_path / "watcher.log"

        collector = LogCollector(log_dir=str(tmp_path))
        collector.start()

        for i in range(5):
            with open(log_file, "a") as f:
                f.write(json.dumps({"component": "watcher", "message": f"m{i}", "level": "INFO", "timestamp": "", "logger": "", "module": "", "func": "", "line": 0}) + "\n")
            time.sleep(0.1)

        time.sleep(1.5)
        count = collector.log_count
        collector.stop()

        assert count >= 5

    def test_running_property(self, tmp_path):
        """running property reflects collector state."""
        collector = LogCollector(log_dir=str(tmp_path))
        assert not collector.running

        collector.start()
        assert collector.running

        collector.stop()
        assert not collector.running

    def test_no_duplicate_setup(self, tmp_path):
        """Starting collector twice is a no-op."""
        collector = LogCollector(log_dir=str(tmp_path))
        collector.start()
        collector.start()  # should not raise
        assert collector.running
        collector.stop()

    def test_file_rotation_detection(self, tmp_path):
        """Collector handles file truncation (rotation) gracefully."""
        log_file = tmp_path / "watcher.log"
        received = []

        collector = LogCollector(
            log_dir=str(tmp_path),
            on_log=lambda doc: received.append(doc),
        )
        collector.start()

        # Write initial content
        log_file.write_text('{"component":"watcher","message":"before","level":"INFO","timestamp":"","logger":"","module":"","func":"","line":0}\n')
        time.sleep(1.0)

        # Simulate rotation: truncate and write new content
        log_file.write_text('{"component":"watcher","message":"after","level":"INFO","timestamp":"","logger":"","module":"","func":"","line":0}\n')
        time.sleep(1.5)

        collector.stop()

        messages = [d["message"] for d in received]
        assert "after" in messages

    def test_on_log_error_doesnt_crash(self, tmp_path):
        """Errors in on_log callback don't crash the collector."""
        call_count = [0]

        def bad_callback(doc):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("boom")

        log_file = tmp_path / "watcher.log"
        collector = LogCollector(
            log_dir=str(tmp_path),
            on_log=bad_callback,
        )
        collector.start()

        # First line triggers error
        with open(log_file, "a") as f:
            f.write('{"component":"watcher","message":"m1","level":"INFO","timestamp":"","logger":"","module":"","func":"","line":0}\n')
        time.sleep(1.0)

        # Second line should succeed
        with open(log_file, "a") as f:
            f.write('{"component":"watcher","message":"m2","level":"INFO","timestamp":"","logger":"","module":"","func":"","line":0}\n')
        time.sleep(1.0)

        collector.stop()

        assert call_count[0] >= 2

    def test_ignores_non_log_files(self, tmp_path):
        """Collector only processes .log files."""
        received = []

        collector = LogCollector(
            log_dir=str(tmp_path),
            on_log=lambda doc: received.append(doc),
        )
        collector.start()

        (tmp_path / "watcher.log").write_text('{"component":"watcher","message":"ok","level":"INFO","timestamp":"","logger":"","module":"","func":"","line":0}\n')
        (tmp_path / "readme.txt").write_text("not a log file\n")
        (tmp_path / ".gitkeep").write_text("")

        time.sleep(1.5)
        collector.stop()

        messages = [d["message"] for d in received]
        assert "ok" in messages
        assert len(received) == 1

    def test_empty_directory(self, tmp_path):
        """Collector handles empty log directory gracefully."""
        collector = LogCollector(log_dir=str(tmp_path))
        collector.start()
        time.sleep(1.0)
        collector.stop()
        assert collector.log_count == 0

    def test_mongo_flush_on_stop(self, tmp_path):
        """Remaining buffered records are flushed to MongoDB on stop."""
        mock_col = MagicMock()
        log_file = tmp_path / "watcher.log"

        collector = LogCollector(
            log_dir=str(tmp_path),
            get_mongo_fn=lambda: mock_col,
        )
        collector.start()

        log_file.write_text('{"component":"watcher","message":"flush_me","level":"INFO","timestamp":"","logger":"","module":"","func":"","line":0}\n')
        time.sleep(1.0)

        # Don't wait for automatic flush — stop should trigger final flush
        collector.stop()

        assert mock_col.insert_many.called
