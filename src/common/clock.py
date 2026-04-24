"""Shared clock — real time or simulated (replay mode).

Used only by the single-process replay controller to set simulated time.
In the pipeline, timestamps flow with events via as_of parameters.
"""
from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware UTC now. Use this instead of datetime.utcnow()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Clock:
    def __init__(self):
        self._simulated: datetime | None = None

    def now(self) -> datetime:
        return self._simulated if self._simulated else utcnow()

    def set_time(self, t):
        if isinstance(t, str):
            self._simulated = datetime.fromisoformat(t.replace("Z", "+00:00")).replace(tzinfo=None)
        elif isinstance(t, datetime):
            self._simulated = t.replace(tzinfo=None) if t.tzinfo else t

    def reset(self):
        self._simulated = None

    @property
    def is_replay(self) -> bool:
        return self._simulated is not None


clock = Clock()
