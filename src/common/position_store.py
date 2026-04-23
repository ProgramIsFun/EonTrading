"""Shared position state via Redis — used in distributed mode."""
import json
import redis


POSITIONS_KEY = "eontrading:positions"


class PositionStore:
    """Read/write current positions via Redis key. Used by Trader (write) and Analyzer (read)."""

    def __init__(self, host: str = "192.168.0.38", port: int = 6379):
        self._redis = redis.Redis(host=host, port=port, decode_responses=True)

    def set_positions(self, positions: dict):
        """Trader calls this on every buy/sell."""
        self._redis.set(POSITIONS_KEY, json.dumps(positions))

    def get_positions(self) -> dict:
        """Analyzer calls this before scoring."""
        data = self._redis.get(POSITIONS_KEY)
        return json.loads(data) if data else {}
