"""Distributed process manager (cross-platform replacement for start_distributed.sh).

Usage:
    python scripts/distributed.py start
    python scripts/distributed.py stop
    python scripts/distributed.py status
    python scripts/distributed.py restart
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PID_DIR = PROJECT_ROOT / "run" / ".pids"
LOG_DIR = PROJECT_ROOT / "logs"

COMPONENTS = {
    "newswatcher": "src.live.runners.run_watcher",
    "analyzer": "src.live.runners.run_analyzer",
    "trader": "src.live.runners.run_trader",
    "executor": "src.live.runners.run_executor",
    "monitor": "src.live.runners.run_monitor",
    "order_tracker": "src.live.runners.run_order_tracker",
}

LOGTAIL_PORT = 8001

VENV_PYTHON = PROJECT_ROOT / ".venv" / "bin" / "python"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)


def _python():
    return str(VENV_PYTHON)


def _load_env():
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        os.environ.setdefault(key, value)


def _write_pid(name: str, pid: int):
    PID_DIR.mkdir(parents=True, exist_ok=True)
    (PID_DIR / f"{name}.pid").write_text(str(pid))


def _read_pid(name: str) -> int | None:
    pid_file = PID_DIR / f"{name}.pid"
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text().strip())
    except (ValueError, OSError):
        return None


def _remove_pid(name: str):
    pid_file = PID_DIR / f"{name}.pid"
    if pid_file.exists():
        pid_file.unlink(missing_ok=True)


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _start_component(name: str, module: str):
    pid = _read_pid(name)
    if pid and _is_alive(pid):
        print(f"  [{name}] already running (pid {pid})")
        return

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.Popen(
        [_python(), "-m", module],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    _write_pid(name, proc.pid)
    print(f"  [{name}] started (pid {proc.pid})")


def _start_api():
    name = "api"
    pid = _read_pid(name)
    if pid and _is_alive(pid):
        print(f"  [{name}] already running (pid {pid})")
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(LOG_DIR / "api.log", "a")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    venv_uvicorn = PROJECT_ROOT / ".venv" / "bin" / "uvicorn"
    cmd = [str(venv_uvicorn), "src.api.server:app", "--host", "0.0.0.0", "--port", "8000"]

    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _write_pid(name, proc.pid)
    print(f"  [{name}] started (pid {proc.pid})")


def _start_logtail():
    name = "logtail"
    pid = _read_pid(name)
    if pid and _is_alive(pid):
        print(f"  [{name}] already running (pid {pid})")
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = open(LOG_DIR / "logtail.log", "a")

    env = os.environ.copy()

    cmd = [_python(), str(PROJECT_ROOT / "scripts" / "logtail.py"),
           "--port", str(LOGTAIL_PORT), "--dir", str(LOG_DIR)]

    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _write_pid(name, proc.pid)
    print(f"  [{name}] started (pid {proc.pid}) — http://localhost:{LOGTAIL_PORT}")


def _stop_process(name: str):
    pid = _read_pid(name)
    if not pid:
        return False

    alive = _is_alive(pid)
    if alive:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass

        for _ in range(30):
            if not _is_alive(pid):
                break
            time.sleep(0.1)
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass

    _remove_pid(name)
    if alive:
        print(f"  [{name}] stopped (pid {pid})")
    return alive


# ── Public API ──────────────────────────────────────────────────────────────


def start_all():
    """Start all distributed components."""
    _load_env()
    print("Starting distributed components...")
    for name, module in COMPONENTS.items():
        _start_component(name, module)
    _start_api()
    _start_logtail()
    print("Done. Use 'python run.py status' to check, 'python run.py stop' to stop.")


def stop_all():
    """Stop all distributed components."""
    print("Stopping all components...")
    any_running = False
    for name in list(COMPONENTS.keys()) + ["api", "logtail"]:
        if _stop_process(name):
            any_running = True
    if not any_running:
        print("  Nothing running.")


def status_all():
    """Show status of all distributed components."""
    running = 0
    total = len(COMPONENTS) + 1
    for name in COMPONENTS:
        pid = _read_pid(name)
        if pid and _is_alive(pid):
            print(f"  [{name}] running (pid {pid})")
            running += 1
        else:
            print(f"  [{name}] stopped")
            _remove_pid(name)

    pid = _read_pid("api")
    if pid and _is_alive(pid):
        print(f"  [api] running (pid {pid})")
        running += 1
    else:
        print(f"  [api] stopped")
        _remove_pid("api")

    pid = _read_pid("logtail")
    if pid and _is_alive(pid):
        print(f"  [logtail] running (pid {pid})")
        running += 1
    else:
        print(f"  [logtail] stopped")
        _remove_pid("logtail")

    if running == 0:
        print("  No components running.")
    elif running == total:
        print(f"  All {running} components running.")
    else:
        print(f"  {running} / {total} components running.")


def restart_all():
    """Restart all distributed components."""
    stop_all()
    time.sleep(1)
    print()
    start_all()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    if cmd == "start":
        start_all()
    elif cmd == "stop":
        stop_all()
    elif cmd == "status":
        status_all()
    elif cmd == "restart":
        restart_all()
    else:
        print(f"Usage: python {__file__} {{start|stop|status|restart}}")
        sys.exit(1)
