"""Log collector — tails per-component log files, writes to MongoDB, broadcasts via callback.

Decoupled from FastAPI — can run embedded in the API server or standalone.
"""
import json
import logging
import os
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
FLUSH_INTERVAL = 2.0


class LogCollector:
    """Tails per-component log files, writes to MongoDB, and calls on_log callback.

    The collector is transport-agnostic: the on_log callback can push to SSE,
    Redis pub/sub, or anything else. No FastAPI imports.

    Args:
        log_dir: Directory containing ``{component}.log`` files.
        get_mongo_fn: Callable returning a PyMongo collection for logs.
            If None, MongoDB writing is disabled.
        on_log: Callback called with each parsed log dict.
            Signature: ``fn(doc: dict) -> None``
    """

    def __init__(
        self,
        log_dir: str = "logs",
        get_mongo_fn: Callable | None = None,
        on_log: Callable[[dict], None] | None = None,
    ):
        self.log_dir = Path(log_dir)
        self._get_mongo_fn = get_mongo_fn
        self._on_log = on_log
        self._running = False
        self._thread: threading.Thread | None = None
        self._offsets: dict[str, int] = {}  # file -> last read position
        self._seen_files: set[str] = set()
        self._mongo_buffer: list[dict] = []
        self._mongo_lock = threading.Lock()
        self._log_count = 0
        self._lock = threading.Lock()

    def start(self):
        """Start the collector in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name="log-collector")
        self._thread.start()
        logger.info("LogCollector started — watching %s", self.log_dir)

    def stop(self):
        """Stop the collector and flush remaining records."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self._flush_mongo()
        logger.info("LogCollector stopped — %d logs processed", self._log_count)

    @property
    def running(self) -> bool:
        return self._running

    @property
    def log_count(self) -> int:
        with self._lock:
            return self._log_count

    def _run(self):
        while self._running:
            try:
                self._scan_files()
                self._flush_mongo()
            except Exception:
                logger.debug("Collector scan error", exc_info=True)
            time.sleep(0.5)

    def _scan_files(self):
        """Scan log directory for new files and new lines."""
        if not self.log_dir.exists():
            return

        for filepath in self.log_dir.glob("*.log"):
            name = filepath.name
            if name not in self._seen_files:
                self._seen_files.add(name)
                # Start reading from beginning of newly discovered files
                self._offsets[name] = 0

            try:
                self._read_new_lines(filepath, name)
            except OSError:
                pass

    def _read_new_lines(self, filepath: Path, name: str):
        """Read new lines from a log file since last offset."""
        size = filepath.stat().st_size
        offset = self._offsets.get(name, 0)

        if size < offset:
            # File was rotated/truncated
            offset = 0

        if size == offset:
            return

        with open(filepath, "r", errors="replace") as f:
            f.seek(offset)
            new_data = f.read()
            self._offsets[name] = f.tell()

        for line in new_data.splitlines():
            line = line.strip()
            if not line:
                continue
            self._process_line(line, name)

    def _process_line(self, line: str, filename: str):
        """Parse a log line and broadcast + buffer for MongoDB."""
        doc = None

        # Try JSON parse (structured mode)
        try:
            doc = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            pass

        if doc is None:
            # Plain text — construct minimal doc
            component = filename.replace(".log", "")
            doc = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "INFO",
                "component": component,
                "logger": "",
                "message": line,
                "module": "",
                "func": "",
                "line": 0,
            }

        # Ensure component is set
        if not doc.get("component"):
            doc["component"] = filename.replace(".log", "")

        with self._lock:
            self._log_count += 1

        # Broadcast via callback
        if self._on_log:
            try:
                self._on_log(doc)
            except Exception:
                pass

        # Buffer for MongoDB
        if self._get_mongo_fn:
            with self._mongo_lock:
                self._mongo_buffer.append(doc)
                if len(self._mongo_buffer) >= BATCH_SIZE:
                    self._flush_mongo()

    def _flush_mongo(self):
        """Flush buffered records to MongoDB."""
        with self._mongo_lock:
            if not self._mongo_buffer:
                return
            docs = self._mongo_buffer[:]
            self._mongo_buffer.clear()

        try:
            col = self._get_mongo_fn()
            insert_docs = []
            for d in docs:
                insert_docs.append({
                    "timestamp": d.get("timestamp", datetime.now(timezone.utc).isoformat()),
                    "level": d.get("level", "INFO"),
                    "logger": d.get("logger", ""),
                    "component": d.get("component", ""),
                    "message": d.get("message", ""),
                    "module": d.get("module", ""),
                    "func": d.get("func", ""),
                    "line": d.get("line", 0),
                })
            col.insert_many(insert_docs, ordered=False)
        except Exception:
            pass  # logging should never crash the app
