#!/bin/bash

echo "Starting OPS Control WebApp Frontend..."

ROSBRIDGE_PID=""
ROSBRIDGE_PID_FILE="/tmp/ops_controlwebapp_rosbridge.pid"
ROSBRIDGE_PORT="9090"

stop_rosbridge_group() {
    local pid="$1"

    if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
        return 0
    fi

    echo "Stopping rosbridge_websocket process group (PID: $pid)..."
    kill -TERM "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true

    for _ in 1 2 3 4 5; do
        if ! kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        sleep 1
    done

    echo "rosbridge_websocket did not stop in time, forcing kill..."
    kill -KILL "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
}

kill_listener_on_rosbridge_port() {
    local pids=""

    if command -v lsof >/dev/null 2>&1; then
        pids="$(lsof -tiTCP:${ROSBRIDGE_PORT} -sTCP:LISTEN 2>/dev/null || true)"
    elif command -v ss >/dev/null 2>&1; then
        pids="$(ss -lptn "sport = :${ROSBRIDGE_PORT}" 2>/dev/null | awk -F'pid=' 'NR>1 && NF>1 {split($2,a,",|"); print a[1]}' | sort -u)"
    fi

    [ -z "$pids" ] && return 0

    echo "Found process(es) listening on port ${ROSBRIDGE_PORT}: $pids"
    for pid in $pids; do
        cmd="$(ps -p "$pid" -o args= 2>/dev/null || true)"
        if echo "$cmd" | grep -Eq "rosbridge|rosbridge_server"; then
            stop_rosbridge_group "$pid"
        else
            echo "Warning: PID $pid on port ${ROSBRIDGE_PORT} is not rosbridge: $cmd"
            echo "Skipping auto-kill for safety."
        fi
    done
}

cleanup() {
    if [ -n "$ROSBRIDGE_PID" ]; then
        stop_rosbridge_group "$ROSBRIDGE_PID"
        wait "$ROSBRIDGE_PID" 2>/dev/null || true
    fi

    rm -f "$ROSBRIDGE_PID_FILE"
}

trap cleanup EXIT SIGINT SIGTERM

# Set up NVM and use Node.js v18
export PATH=/home/legendary/.nvm/versions/node/v18.20.8/bin:$PATH

echo "Node.js version: $(node -v)"
echo "npm version: $(npm -v)"

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
FRONTEND_DIR="$SCRIPT_DIR"

cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
    echo "Installing Node.js dependencies..."
    npm install
fi

if [ -f "$ROSBRIDGE_PID_FILE" ]; then
    OLD_PID="$(cat "$ROSBRIDGE_PID_FILE" 2>/dev/null)"
    if [ -n "$OLD_PID" ]; then
        echo "Found stale rosbridge PID file ($OLD_PID), cleaning up..."
        stop_rosbridge_group "$OLD_PID"
    fi
    rm -f "$ROSBRIDGE_PID_FILE"
fi

kill_listener_on_rosbridge_port

echo "Starting rosbridge_websocket as frontend subprocess..."
setsid bash -lc 'source /opt/ros/${ROS_DISTRO}/setup.bash && ros2 launch rosbridge_server rosbridge_websocket_launch.xml address:=0.0.0.0' &
ROSBRIDGE_PID=$!
echo "$ROSBRIDGE_PID" > "$ROSBRIDGE_PID_FILE"
sleep 2
echo "rosbridge_websocket started with PID: $ROSBRIDGE_PID"

echo "Starting Vite development server on port 3000..."
npm run dev -- --port 3000 --host 0.0.0.0

