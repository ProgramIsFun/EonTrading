#!/usr/bin/env bash
# Start/stop all 7 distributed components outside Docker.
# Usage:
#   ./scripts/start_distributed.sh start          # start all processes
#   ./scripts/start_distributed.sh stop           # kill all processes
#   ./scripts/start_distributed.sh status         # show running processes
#   ./scripts/start_distributed.sh restart        # stop + start
set -euo pipefail

cd "$(dirname "$0")/.."
PID_DIR="run/.pids"
LOG_DIR="logs"
PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
COMPONENTS=(
    "watcher:src.live.runners.run_watcher"
    "analyzer:src.live.runners.run_analyzer"
    "trader:src.live.runners.run_trader"
    "executor:src.live.runners.run_executor"
    "monitor:src.live.runners.run_monitor"
    "order_tracker:src.live.runners.run_order_tracker"
)
API_CMD="uvicorn src.api.server:app --host 0.0.0.0 --port 8000"

mkdir -p "$PID_DIR" "$LOG_DIR"

# Source .env if present
if [ -f .env ]; then
    set -a
    # shellcheck disable=1091
    . .env
    set +a
fi

_pid_file() { echo "$PID_DIR/$1.pid"; }
_log_file() { echo "$LOG_DIR/$1.log"; }

start_component() {
    local name="$1" module="$2"
    local pid_file="$PID_DIR/$name.pid"
    local log_file="$LOG_DIR/$name.log"
    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "  [$name] already running (pid $(cat "$pid_file"))"
        return
    fi
    # Start in background with restart loop
    nohup bash -c "
        cd '$PWD'
        export PYTHONPATH='$PYTHONPATH'
        while true; do
            echo \"\$ (date -Iseconds) Starting $name...\" >> '$log_file'
            python -m '$module' >> '$log_file' 2>&1
            rc=\$?
            echo \"\$ (date -Iseconds) $name exited with code \$rc, restarting in 3s...\" >> '$log_file'
            sleep 3
        done
    " > /dev/null 2>&1 &
    local pid=$!
    echo "$pid" > "$pid_file"
    echo "  [$name] started (pid $pid)"
}

start_api() {
    local pid_file="$PID_DIR/api.pid"
    local log_file="$LOG_DIR/api.log"
    if [ -f "$pid_file" ] && kill -0 "$(cat "$pid_file")" 2>/dev/null; then
        echo "  [api] already running (pid $(cat "$pid_file"))"
        return
    fi
    nohup bash -c "
        cd '$PWD'
        export PYTHONPATH='$PYTHONPATH'
        while true; do
            echo \"\$ (date -Iseconds) Starting API server...\" >> '$log_file'
            $API_CMD >> '$log_file' 2>&1
            rc=\$?
            echo \"\$ (date -Iseconds) API exited with code \$rc, restarting in 3s...\" >> '$log_file'
            sleep 3
        done
    " > /dev/null 2>&1 &
    local pid=$!
    echo "$pid" > "$pid_file"
    echo "  [api] started (pid $pid)"
}

stop_all() {
    local any=false
    for entry in "${COMPONENTS[@]}"; do
        name="${entry%%:*}"
        local pid_file="$PID_DIR/$name.pid"
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            kill "$pid" 2>/dev/null && echo "  [$name] stopped (pid $pid)" || true
            rm -f "$pid_file"
            any=true
        fi
    done
    # Stop API
    if [ -f "$PID_DIR/api.pid" ]; then
        pid=$(cat "$PID_DIR/api.pid")
        kill "$pid" 2>/dev/null && echo "  [api] stopped (pid $pid)" || true
        rm -f "$PID_DIR/api.pid"
        any=true
    fi
    # Kill any process groups still running
    pkill -f "src.live.runners.run_" 2>/dev/null || true
    pkill -f "uvicorn.*src.api.server" 2>/dev/null || true
    $any || echo "  Nothing running."
}

status_all() {
    local running=0
    for entry in "${COMPONENTS[@]}"; do
        name="${entry%%:*}"
        local pid_file="$PID_DIR/$name.pid"
        if [ -f "$pid_file" ] && pid=$(cat "$pid_file") && kill -0 "$pid" 2>/dev/null; then
            echo "  [$name] running (pid $pid)"
            running=$((running + 1))
        else
            echo "  [$name] stopped"
            rm -f "$pid_file"
        fi
    done
    if [ -f "$PID_DIR/api.pid" ] && pid=$(cat "$PID_DIR/api.pid") && kill -0 "$pid" 2>/dev/null; then
        echo "  [api] running (pid $pid)"
        running=$((running + 1))
    else
        echo "  [api] stopped"
        rm -f "$PID_DIR/api.pid"
    fi
    if [ $running -eq 0 ]; then
        echo "  No components running."
    elif [ $running -eq $(( ${#COMPONENTS[@]} + 1 )) ]; then
        echo "  All $running components running."
    else
        echo "  $running / $(( ${#COMPONENTS[@]} + 1 )) components running."
    fi
}

case "${1:-start}" in
    start)
        echo "Starting distributed components..."
        # Kill stale processes first
        for entry in "${COMPONENTS[@]}"; do
            name="${entry%%:*}"; module="${entry#*:}"
            start_component "$name" "$module"
        done
        start_api
        echo "Done. Use '$0 status' to check, '$0 stop' to stop."
        ;;
    stop)
        echo "Stopping all components..."
        stop_all
        ;;
    status)
        status_all
        ;;
    restart)
        echo "Restarting all components..."
        stop_all
        sleep 1
        echo ""
        $0 start
        ;;
    *)
        echo "Usage: $0 {start|stop|status|restart}"
        exit 1
        ;;
esac
