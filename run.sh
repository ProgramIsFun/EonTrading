#!/usr/bin/env bash
# Usage:
#   ./run.sh              # single process (default)
#   ./run.sh stop         # kill all distributed processes
set -e
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"

case "${1:-single}" in
  single)
    echo "Starting single-process mode..."
    python3 -m src.live.news_trader
    ;;
  stop)
    pkill -f "src.live.runners.run_" 2>/dev/null && echo "Stopped." || echo "Nothing running."
    ;;
  *)
    echo "Usage: ./run.sh [single|stop]"
    ;;
esac
