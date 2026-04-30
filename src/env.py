"""Environment config — reads from env vars, falls back to platform-based defaults."""
import os
import platform

_is_mac = platform.system() == "Darwin"
_default_remote = "localhost" if _is_mac else "192.168.0.38"

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", _default_remote if not _is_mac else "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DB", "eontrading")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost" if _is_mac else _default_remote)
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))


def env_bool(key: str, default: bool = False) -> bool:
    """Read a boolean env var. Treats '1', 'true', 'yes' as True, everything else as False."""
    val = os.getenv(key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes")
