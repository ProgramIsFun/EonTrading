#!/usr/bin/env bash
# Usage:
#   ./run.sh              # single process (default)
#   ./run.sh distributed  # 4 separate processes
#   ./run.sh stop         # kill all distributed processes
set -e
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"

case "${1:-single}" in
  single)
    echo "Starting single-process mode..."
    python3 -m src.live.news_trader
    ;;
  distributed)
    echo "Starting distributed mode (4 processes)..."
    python3 -m src.live.runners.run_watcher &
    python3 -m src.live.runners.run_analyzer &
    python3 -m src.live.runners.run_trader &
    python3 -m src.live.runners.run_executor &
    echo "All runners started. PIDs: $(jobs -p)"
    echo "Run './run.sh stop' to kill all."
    wait
    ;;
  stop)
    pkill -f "src.live.runners.run_" 2>/dev/null && echo "Stopped." || echo "Nothing running."
    ;;
  *)
    echo "Usage: ./run.sh [single|distributed|stop]"
    ;;
esac
