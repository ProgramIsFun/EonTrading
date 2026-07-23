"""Open terminal windows tailing each log file.

Usage:  python scripts/tail_logs.py
"""
import subprocess
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"

# All known components — tail even if file doesn't exist yet
COMPONENTS = [
    "newswatcher", "analyzer", "trader", "executor",
    "monitor", "order_tracker", "api",
]


def is_already_tailing(filepath: str) -> bool:
    """Check if tail -f is already running on this file."""
    try:
        out = subprocess.check_output(["pgrep", "-af", "tail"], text=True, stderr=True)
        return filepath in out
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def open_terminal(title: str, cmd: list[str]):
    if sys.platform == "darwin":
        script = f'tell application "Terminal" to do script "{" ".join(cmd)}"'
        subprocess.Popen(["osascript", "-e", script])
    elif sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", title, "cmd", "/k"] + cmd)
    else:
        subprocess.Popen(["gnome-terminal", "--title", title, "--"] + cmd)


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    opened = 0
    skipped = 0
    for name in COMPONENTS:
        log = LOG_DIR / f"{name}.log"
        log.touch(exist_ok=True)
        if is_already_tailing(str(log)):
            print(f"  [{name}] already running, skipping")
            skipped += 1
            continue
        open_terminal(name, ["tail", "-f", str(log)])
        print(f"  [{name}] {log}")
        opened += 1
    print(f"Opened {opened} terminals ({skipped} already running).")


if __name__ == "__main__":
    main()
