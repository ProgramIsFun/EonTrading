"""Open terminal windows tailing each log file.

Usage:  python scripts/tail_logs.py
"""
import subprocess
import sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def open_terminal(title: str, cmd: list[str]):
    if sys.platform == "darwin":
        script = f'tell application "Terminal" to do script "{" ".join(cmd)}"'
        subprocess.Popen(["osascript", "-e", script])
    elif sys.platform == "win32":
        subprocess.Popen(["cmd", "/c", "start", title, "cmd", "/k"] + cmd)
    else:
        subprocess.Popen(["gnome-terminal", "--title", title, "--"] + cmd)


def main():
    logs = sorted(LOG_DIR.glob("*.log"))
    if not logs:
        print(f"No log files in {LOG_DIR}")
        return
    for log in logs:
        title = log.stem
        open_terminal(title, ["tail", "-f", str(log)])
        print(f"  [{title}] {log}")
    print(f"Opened {len(logs)} terminals.")


if __name__ == "__main__":
    main()
