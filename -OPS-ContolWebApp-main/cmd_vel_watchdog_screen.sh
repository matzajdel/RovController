#!/usr/bin/env bash
set -u

SESSION_NAME="${SCREEN_SESSION_NAME:-cmd_vel_watchdog}"
SELF_PATH="$(readlink -f "$0")"

if [[ "${1:-}" != "--worker" ]]; then
  if ! command -v screen >/dev/null 2>&1; then
    echo "Error: 'screen' is not installed."
    exit 1
  fi

  if screen -list | grep -q "[[:space:]]${SESSION_NAME}[[:space:]]"; then
    echo "screen session '${SESSION_NAME}' is already running."
    exit 0
  fi

  screen -dmS "${SESSION_NAME}" bash "${SELF_PATH}" --worker
  echo "Started watchdog in screen session '${SESSION_NAME}'."
  echo "Attach with: screen -r ${SESSION_NAME}"
  echo "Stop with:   screen -S ${SESSION_NAME} -X quit"
  exit 0
fi

if ! command -v ros2 >/dev/null 2>&1; then
  echo "Error: 'ros2' not found in PATH inside screen session."
  exit 1
fi

echo "[watchdog] Listening on /cmd_vel (2s timeout)."
echo "[watchdog] On timeout: publishing zero to /cmd_vel and /array_topic."

while true; do
  if timeout 2s ros2 topic echo --once /cmd_vel >/dev/null 2>&1; then
    # Message received in time, do nothing.
    continue
  fi

  echo "[watchdog] Timeout. Publishing STOP zeros."

  ros2 topic pub --once /cmd_vel geometry_msgs/msg/Twist \
    "{linear: {x: 0.0, y: 0.0, z: 0.0}, angular: {x: 0.0, y: 0.0, z: 0.0}}" \
    >/dev/null 2>&1 || true

  ros2 topic pub --once /array_topic std_msgs/msg/Float64MultiArray \
    "{data: [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]}" \
    >/dev/null 2>&1 || true

done
