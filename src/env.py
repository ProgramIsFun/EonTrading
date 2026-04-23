"""Environment config — auto-detects Mac vs Windows PC."""
import platform

_is_mac = platform.system() == "Darwin"

CLICKHOUSE_HOST = "localhost" if _is_mac else "192.168.0.38"
CLICKHOUSE_PORT = 8123
CLICKHOUSE_DB = "eontrading"

REDIS_HOST = "localhost" if _is_mac else "192.168.0.38"
REDIS_PORT = 6379
