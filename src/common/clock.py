"""Shared clock — real time or simulated (replay mode).

Used only by the single-process replay controller to set simulated time.
In the pipeline, timestamps flow with events via as_of parameters.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC now. Use this instead of datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_dt(value, *, strip_tz: bool = False) -> datetime | None:
    """Parse ISO-8601 timestamps (e.g. "2025-01-02T03:04:05Z") into datetimes.

    Returns None for empty or unparseable input. Keeps tzinfo by default;
    pass strip_tz=True to get a naive datetime.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if strip_tz else value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed.replace(tzinfo=None) if strip_tz else parsed


class Clock:
    def __init__(self):
        self._simulated: datetime | None = None

    def now(self) -> datetime:
        return self._simulated if self._simulated else utcnow()

    def set_time(self, t):
        if isinstance(t, str):
            parsed = parse_dt(t, strip_tz=True)
            if parsed is None:
                raise ValueError(f"Invalid timestamp: {t!r}")
            self._simulated = parsed
        elif isinstance(t, datetime):
            self._simulated = t.replace(tzinfo=None) if t.tzinfo else t

    def reset(self):
        self._simulated = None

    @property
    def is_replay(self) -> bool:
        return self._simulated is not None


clock = Clock()
