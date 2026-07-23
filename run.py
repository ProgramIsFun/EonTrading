#!/usr/bin/env python3
"""EonTrading CLI — cross-platform replacement for run.sh.

Usage:
    python run.py                # single process (default)
    python run.py start          # distributed mode — start all 7 components
    python run.py stop           # kill all distributed processes
    python run.py status         # show running processes
    python run.py restart        # stop + start
    python run.py clean          # delete all log files
    python run.py logs           # open terminal windows tailing each log file
"""
import os
import signal
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent


def _setup_path():
    """Ensure project root is on sys.path and env."""
    root = str(PROJECT_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ["PYTHONPATH"] = root + os.pathsep + os.environ.get("PYTHONPATH", "")


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


def cmd_single():
    _setup_path()
    _load_env()
    from src.live.news_trader import main_single
    import asyncio
    asyncio.run(main_single())


def cmd_start():
    _setup_path()
    _load_env()
    _kill_single_process()
    from scripts.distributed import start_all
    start_all()


def _kill_single_process():
    """Kill single-process mode if running (psutil-free, cross-platform)."""
    try:
        out = subprocess.check_output(
            ["pgrep", "-af", "news_trader"], text=True, stderr=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return
    for line in out.strip().splitlines():
        pid_str = line.split()[0]
        try:
            pid = int(pid_str)
            print(f"  Killing single-process (pid {pid})...")
            os.kill(pid, signal.SIGTERM)
        except (ValueError, ProcessLookupError, PermissionError):
            pass


def cmd_stop():
    _setup_path()
    _load_env()
    from scripts.distributed import stop_all
    stop_all()


def cmd_status():
    _setup_path()
    _load_env()
    from scripts.distributed import status_all
    status_all()


def cmd_restart():
    _setup_path()
    _load_env()
    _kill_single_process()
    from scripts.distributed import restart_all
    restart_all()


def cmd_clean():
    log_dir = PROJECT_ROOT / "logs"
    if not log_dir.exists():
        print("No logs/ directory.")
        return
    logs = list(log_dir.glob("*.log"))
    if not logs:
        print("No log files to clean.")
        return
    for f in logs:
        f.unlink()
        print(f"  deleted {f.name}")
    print(f"Cleaned {len(logs)} log files.")


def cmd_logs():
    from scripts.tail_logs import main as tail_main
    tail_main()


COMMANDS = {
    "single": cmd_single,
    "start": cmd_start,
    "stop": cmd_stop,
    "status": cmd_status,
    "restart": cmd_restart,
    "clean": cmd_clean,
    "logs": cmd_logs,
}


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "single"
    if cmd in ("-h", "--help", "help"):
        print(__doc__.strip())
        sys.exit(0)
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}")
        print(f"Usage: python run.py {{{'|'.join(COMMANDS)}}}")
        sys.exit(1)
    COMMANDS[cmd]()


if __name__ == "__main__":
    main()
