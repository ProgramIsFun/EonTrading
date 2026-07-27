"""Structured logging setup — console + per-component file + optional JSON format."""
import json
import logging
import logging.handlers
import traceback
from datetime import datetime, timezone
from pathlib import Path


class ComponentFilter(logging.Filter):
    """Adds a *component* attribute to every log record."""

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
        super().__init__(fmt, datefmt, style)  # type: ignore[arg-type]
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


class JsonFormatter(logging.Formatter):
    """Structured JSON formatter — one JSON object per line.

    Used by the log collector for machine-parseable output.
    """

    def format(self, record: logging.LogRecord) -> str:
        doc = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", ""),
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info and record.exc_info[1] is not None:
            doc["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "Unknown",
                "message": str(record.exc_info[1]),
                "traceback": "".join(traceback.format_exception(*record.exc_info)),
            }
        return json.dumps(doc, ensure_ascii=False)


def _make_formatter():
    """Create the appropriate formatter based on settings."""
    from src.settings import settings
    if settings.log_output == "json":
        return JsonFormatter()
    return ComponentFormatter(log_format=settings.log_format, datefmt="%H:%M:%S")


def setup_logging(component: str | None = None, log_dir: str = "logs"):
    """One-call setup: console + per-component file logging.

    Safe to call multiple times with different component names (single-process
    mode). Duplicate calls for the same component are ignored.

    Args:
        component: Component name (e.g. "newswatcher", "analyzer"). If given,
            creates a ``FileHandler`` writing to ``logs/{component}.log``.
            If ``None``, only console logging is set up (used by API server).
        log_dir: Directory for log files.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Track which components already have file handlers
    existing: set[str] = getattr(root, "_eon_components", set())
    if component and component in existing:
        return

    fmt = _make_formatter()

    # Console handler — added once
    if not getattr(root, "_eon_console_added", False):
        setattr(root, "_eon_console_added", True)
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        root.addHandler(console)

    # Per-component file handler
    if component:
        existing.add(component)
        setattr(root, "_eon_components", existing)
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            Path(log_dir) / f"{component}.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
