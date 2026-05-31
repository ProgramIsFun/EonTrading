"""Buffered MongoDB log handler — fast, non-blocking, batch writes."""
import logging
import queue
import threading
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any


class ComponentFilter(logging.Filter):
    """Adds a *component* attribute to every log record.

    Usage::

        handler.addFilter(ComponentFilter("watcher"))
    """
    def __init__(self, component: str):
        super().__init__()
        self.component = component

    def filter(self, record: logging.LogRecord) -> bool:
        record.component = self.component
        return True


COMPONENT_FORMAT = "%(asctime)s [%(component_or_name)s] %(levelname)s: %(message)s"


class ComponentFormatter(logging.Formatter):
    """Formatter that shows ``[component]``, ``[name]``, or ``[component:name]``.

    Controlled by the ``log_format`` setting (``"component"``, ``"module"``,
    or ``"both"``).  Falls back to module name when the record has no
    *component* attribute.
    """
    def __init__(self, fmt: str = COMPONENT_FORMAT, datefmt: str | None = None,
                 style: str = "%", log_format: str = "both"):
        super().__init__(fmt, datefmt, style)
        self.log_format = log_format

    def format(self, record: logging.LogRecord) -> str:
        comp = getattr(record, "component", "")
        if comp:
            if self.log_format == "component":
                record.component_or_name = comp
            elif self.log_format == "module":
                record.component_or_name = record.name
            else:  # "both"
                record.component_or_name = f"{comp}:{record.name}"
        else:
            record.component_or_name = record.name
        return super().format(record)


def setup_logging():
    """One-call setup: console logging with *component* format + MongoDB handler.

    Reads ``settings.log_format`` to control the console label:

    * ``"both"`` (default) — ``[watcher:src.live.news_watcher]``
    * ``"component"`` — ``[watcher]``
    * ``"module"`` — ``[src.live.news_watcher]``

    Intended as a drop-in replacement for the manual ``basicConfig`` +
    ``maybe_enable_mongo_logging`` pattern used in every runner::

        from src.common.log_handler import setup_logging
        setup_logging()
    """
    from src.settings import settings
    fmt = ComponentFormatter(log_format=settings.log_format, datefmt="%H:%M:%S")
    handler = logging.StreamHandler()
    handler.setFormatter(fmt)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    maybe_enable_mongo_logging()


def maybe_enable_mongo_logging():
    """Add MongoBatchHandler to root logger if MONGODB_LOG is enabled.

    Call once at startup in each process entry point.
    """
    from src.settings import settings
    if not settings.mongodb_log:
        return
    from src.data.utils.db_helper import get_mongo_client
    get_mongo_client()  # warm cache so handler doesn't trigger recursive logging
    handler = MongoBatchHandler()
    handler.start()
    logging.getLogger().addHandler(handler)


class MongoBatchHandler(logging.Handler):
    """Log handler that batches records and flushes to MongoDB with insert_many.

    emit() is fast — just appends to a deque. A background thread drains the
    queue and flushes every `flush_interval` seconds or when `batch_size` is
    reached, whichever comes first.
    """
    BATCH_SIZE = 100
    FLUSH_INTERVAL = 2.0

    def __init__(self, level=logging.INFO, batch_size: int = None, flush_interval: float = None,
                 get_col: Callable[[], Any] = None):
        super().__init__(level)
        self._queue: queue.SimpleQueue[logging.LogRecord] = queue.SimpleQueue()
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._batch_size = batch_size or self.BATCH_SIZE
        self._flush_interval = flush_interval or self.FLUSH_INTERVAL
        self._get_col = get_col or self._default_col

    def _default_col(self):
        from src.data.utils.db_helper import get_mongo_client
        return get_mongo_client()["EonTradingDB"]["logs"]

    def emit(self, record: logging.LogRecord):
        self._queue.put_nowait(record)

    def _run(self):
        while not self._done.is_set():
            records = self._drain()
            if records:
                self._flush(records)
            self._done.wait(self._flush_interval)

    def _drain(self) -> list[logging.LogRecord]:
        records = []
        while len(records) < self._batch_size:
            try:
                records.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return records

    def _flush(self, records: list[logging.LogRecord]):
        try:
            docs = []
            for r in records:
                docs.append({
                    "timestamp": datetime.utcnow(),
                    "level": r.levelname,
                    "logger": r.name,
                    "component": getattr(r, "component", ""),
                    "message": r.getMessage(),
                    "module": r.module,
                    "func": r.funcName,
                    "line": r.lineno,
                })
            self._get_col().insert_many(docs, ordered=False)
        except Exception:
            pass  # fail silently — logging should never crash the app

    def close(self):
        # Flush remaining records before shutdown
        records = self._drain()
        if records:
            self._flush(records)
        self._done.set()
        self._thread.join(timeout=5)
        super().close()

    def start(self):
        self._thread.start()
