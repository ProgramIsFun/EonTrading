#!/usr/bin/env bash
# Usage:
#   ./run.sh                       # single process (default)
#   ./run.sh start                 # distributed mode — start all 7 components
#   ./run.sh stop                  # kill all distributed processes
#   ./run.sh status                # show running processes
#   ./run.sh restart               # stop + start
set -e
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"

case "${1:-single}" in
  single)
    echo "Starting single-process mode..."
    python3 -m src.live.news_trader
    ;;
  start)
    shift
    exec ./scripts/start_distributed.sh start "$@"
    ;;
  stop)
    pkill -f "src.live.runners.run_" 2>/dev/null && echo "Stopped." || echo "Nothing running."
    pkill -f "uvicorn.*src.api.server" 2>/dev/null || true
    ;;
  status)
    exec ./scripts/start_distributed.sh status
    ;;
  restart)
    exec ./scripts/start_distributed.sh restart
    ;;
  *)
    echo "Usage: $0 [single|start|stop|status|restart]"
    ;;
esac
