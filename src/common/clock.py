"""Shared clock — real time or simulated (replay mode).

Usage:
  from src.common.clock import clock

  clock.now()                    # live: datetime.utcnow()
  clock.set_time("2025-04-03T14:00:00Z")  # replay: returns that time
  clock.reset()                  # back to live mode
"""
from datetime import datetime


class Clock:
    """Global clock. Defaults to real time. Set simulated time for replay mode."""

    def __init__(self):
        self._simulated: datetime | None = None

    def now(self) -> datetime:
        return self._simulated if self._simulated else datetime.utcnow()

    def set_time(self, t):
        """Set simulated time. Accepts datetime or ISO string."""
        if isinstance(t, str):
            self._simulated = datetime.fromisoformat(t.replace("Z", "+00:00")).replace(tzinfo=None)
        elif isinstance(t, datetime):
            self._simulated = t.replace(tzinfo=None) if t.tzinfo else t
        else:
            raise ValueError(f"Expected datetime or ISO string, got {type(t)}")

    def reset(self):
        """Back to real time."""
        self._simulated = None

    @property
    def is_replay(self) -> bool:
        return self._simulated is not None


# Global singleton — import this everywhere
clock = Clock()
