"""Docker Compose management — start/stop/status of pipeline containers."""
import subprocess
import os

# Path to docker-compose.yml — same directory as the project root
COMPOSE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

COMPONENTS = ["watcher", "analyzer", "trader", "executor", "redis"]


def _run(cmd: list[str], timeout: int = 30, env: dict = None) -> dict:
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=COMPOSE_DIR, env=env,
        )
        return {"ok": result.returncode == 0, "stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "stdout": "", "stderr": "docker not found"}


def container_status() -> list[dict]:
    """Get status of all compose services."""
    result = _run(["docker", "compose", "ps", "--format", "json", "-a"])
    if not result["ok"]:
        return []
    import json
    containers = []
    for line in result["stdout"].splitlines():
        try:
            c = json.loads(line)
            containers.append({
                "name": c.get("Service", c.get("Name", "")),
                "state": c.get("State", ""),
                "status": c.get("Status", ""),
            })
        except json.JSONDecodeError:
            pass
    return containers


def start_component(name: str, profile: str = "distributed", env: dict = None) -> dict:
    """Start a single service (or 'all' for the full profile)."""
    extra_env = {**os.environ, **(env or {})}
    if name == "all":
        return _run(["docker", "compose", "--profile", profile, "up", "-d"], env=extra_env)
    if name == "redis":
        return _run(["docker", "compose", "up", "-d", "redis"], env=extra_env)
    return _run(["docker", "compose", "--profile", profile, "up", "-d", name], env=extra_env)


def stop_component(name: str) -> dict:
    """Stop a single service (or 'all')."""
    if name == "all":
        return _run(["docker", "compose", "--profile", "distributed", "down"])
    return _run(["docker", "compose", "stop", name])


def restart_component(name: str) -> dict:
    """Restart a single service."""
    return _run(["docker", "compose", "restart", name])


def view_logs(name: str, lines: int = 50) -> dict:
    """Get recent logs for a service."""
    return _run(["docker", "compose", "logs", "--tail", str(lines), name])
