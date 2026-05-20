#!/bin/bash
# Start/stop robot cameras using GNU screen sessions
# Each camera runs in its own screen session for easy management
# Compatible with web app on/off control via API

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─── Camera configuration ────────────────────────────────────────────
CAMERA_DEVICES=( "/dev/video0" "/dev/video2" "/dev/video4" "/dev/video6" )
CAMERA_PORTS=(   8081          8082          8083          8084         )
CAMERA_NAMES=(   "Camera-1"    "Camera-2"    "Camera-3"    "Camera-4"  )
SCREEN_PREFIX="cam"

RESOLUTION="640x480"
FRAMERATE=15
# -y = force YUYV input format, -q 50 = JPEG quality 50
EXTRA_INPUT_FLAGS="-y -q 50"

# ─── Helpers ──────────────────────────────────────────────────────────
screen_name() { echo "${SCREEN_PREFIX}${1}"; }

is_running() {
    screen -ls "$(screen_name "$1")" 2>/dev/null | grep -q "$(screen_name "$1")"
}

find_plugin_dir() {
    for dir in /usr/local/lib/mjpg-streamer /usr/lib/mjpg-streamer; do
        [ -d "$dir" ] && echo "$dir" && return
    done
}

# ─── Start a single camera ───────────────────────────────────────────
start_camera() {
    local idx=$1  # 1-based camera number
    local arr_idx=$((idx - 1))
    local device="${CAMERA_DEVICES[$arr_idx]}"
    local port="${CAMERA_PORTS[$arr_idx]}"
    local name="${CAMERA_NAMES[$arr_idx]}"
    local session
    session="$(screen_name "$idx")"

    if is_running "$idx"; then
        echo "  [SKIP] $name ($session) is already running"
        return 0
    fi

    if [ ! -e "$device" ]; then
        echo "  [WARN] $name device not found: $device"
        return 1
    fi

    local plugin_dir
    plugin_dir="$(find_plugin_dir)"

    local cmd="export LD_LIBRARY_PATH=${plugin_dir}:\$LD_LIBRARY_PATH; "
    cmd+="mjpg_streamer "
    cmd+="-i \"input_uvc.so -d ${device} -r ${RESOLUTION} -f ${FRAMERATE} ${EXTRA_INPUT_FLAGS}\" "
    cmd+="-o \"output_http.so -p ${port}\""

    screen -dmS "$session" bash -lc "$cmd"
    sleep 1

    if is_running "$idx"; then
        local ip
        ip=$(hostname -I | awk '{print $1}')
        echo "  [OK]   $name  screen=$session  http://${ip}:${port}/?action=stream"
    else
        echo "  [FAIL] $name could not start. Check:  screen -r $session"
        return 1
    fi
}

# ─── Stop a single camera ────────────────────────────────────────────
stop_camera() {
    local idx=$1
    local name="${CAMERA_NAMES[$((idx - 1))]}"
    local session
    session="$(screen_name "$idx")"

    if ! is_running "$idx"; then
        echo "  [SKIP] $name ($session) is not running"
        return 0
    fi

    screen -S "$session" -X quit 2>/dev/null
    sleep 0.5
    # Belt-and-suspenders: kill leftover mjpg_streamer on that port
    local port="${CAMERA_PORTS[$((idx - 1))]}"
    fuser -k -n tcp "$port" 2>/dev/null || true

    echo "  [OK]   $name ($session) stopped"
}

# ─── Status ───────────────────────────────────────────────────────────
show_status() {
    echo ""
    echo "Camera Screen Sessions"
    echo "──────────────────────────────────────────────"
    local ip
    ip=$(hostname -I | awk '{print $1}')
    for i in $(seq 1 ${#CAMERA_DEVICES[@]}); do
        local arr_idx=$((i - 1))
        local session
        session="$(screen_name "$i")"
        local name="${CAMERA_NAMES[$arr_idx]}"
        local port="${CAMERA_PORTS[$arr_idx]}"
        local device="${CAMERA_DEVICES[$arr_idx]}"
        if is_running "$i"; then
            echo "  $name  [$session]  RUNNING   http://${ip}:${port}/?action=stream  ($device)"
        else
            echo "  $name  [$session]  STOPPED   port ${port}  ($device)"
        fi
    done
    echo ""
}

# ─── Usage ────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
Usage: $(basename "$0") <command> [camera_number]

Commands:
  start   [N]   Start all cameras, or camera N (1-4)
  stop    [N]   Stop all cameras, or camera N (1-4)
  restart [N]   Restart all cameras, or camera N (1-4)
  status        Show running camera screens

Examples:
  $(basename "$0") start          # start all cameras
  $(basename "$0") start 2        # start only Camera-2
  $(basename "$0") stop 3         # stop only Camera-3
  $(basename "$0") restart        # restart all cameras
  $(basename "$0") status         # list camera screen sessions

Flags applied to mjpg_streamer input_uvc:
  -y      force YUYV input format
  -q 50   JPEG quality 50
EOF
}

# ─── Pre-flight checks ───────────────────────────────────────────────
preflight() {
    if ! command -v screen &>/dev/null; then
        echo "ERROR: 'screen' is not installed.  sudo apt install screen"
        exit 1
    fi
    if ! command -v mjpg_streamer &>/dev/null; then
        echo "ERROR: 'mjpg_streamer' is not installed."
        echo "  sudo apt install -y cmake libjpeg-dev gcc g++ git"
        echo "  cd /tmp && git clone https://github.com/jacksonliam/mjpg-streamer.git"
        echo "  cd mjpg-streamer/mjpg-streamer-experimental && make && sudo make install"
        exit 1
    fi
}

# ─── Main ─────────────────────────────────────────────────────────────
main() {
    local action="${1:-}"
    local cam_num="${2:-}"

    case "$action" in
        start)
            preflight
            echo "Starting cameras..."
            if [ -n "$cam_num" ]; then
                start_camera "$cam_num"
            else
                for i in $(seq 1 ${#CAMERA_DEVICES[@]}); do
                    start_camera "$i"
                done
            fi
            show_status
            ;;
        stop)
            echo "Stopping cameras..."
            if [ -n "$cam_num" ]; then
                stop_camera "$cam_num"
            else
                for i in $(seq 1 ${#CAMERA_DEVICES[@]}); do
                    stop_camera "$i"
                done
            fi
            show_status
            ;;
        restart)
            echo "Restarting cameras..."
            if [ -n "$cam_num" ]; then
                stop_camera "$cam_num"
                sleep 1
                start_camera "$cam_num"
            else
                for i in $(seq 1 ${#CAMERA_DEVICES[@]}); do
                    stop_camera "$i"
                done
                sleep 1
                for i in $(seq 1 ${#CAMERA_DEVICES[@]}); do
                    start_camera "$i"
                done
            fi
            show_status
            ;;
        status)
            show_status
            ;;
        *)
            usage
            exit 1
            ;;
    esac
}

main "$@"
