#!/bin/bash

# Web resolution and framerate
WEB_RESOLUTION="640x480"
WEB_FRAMERATE="15"

echo "==================================================="
echo "Starting MJPG-Streamer for Web Frontend"
echo "==================================================="

# Default ports matches camera_config.py
PORTS=(8081 8082 8083 8084)
# Devices
DEVICES=("/dev/video0" "/dev/video2" "/dev/video4" "/dev/video6")

# Ensure screen is installed
if ! command -v screen &> /dev/null; then
    echo "Error: 'screen' is not installed. Please install it with: sudo apt install screen"
    exit 1
fi

# Ensure mjpg_streamer is installed
if ! command -v mjpg_streamer &> /dev/null; then
    echo "Error: 'mjpg_streamer' is not installed."
    exit 1
fi

cam_index=0
for device in "${DEVICES[@]}"; do
    cam_num=$((cam_index + 1))
    port=${PORTS[$cam_index]}
    cam_name="Kamera $cam_num"
    session_name="mjpg_cam$cam_num"
    
    if [ -e "$device" ]; then
        echo "--> Found device $device. Configuring $cam_name on port $port..."
        
        # Kill existing screen if any
        screen -S "$session_name" -X quit 2>/dev/null
        # Kill existing mjpg_streamer on this port
        pkill -f "mjpg_streamer.*-p $port" 2>/dev/null
        sleep 0.5
        
        CMD="mjpg_streamer -i 'input_uvc.so -d $device -r $WEB_RESOLUTION -f $WEB_FRAMERATE -y -q 50' -o 'output_http.so -p $port'"
        
        # Start in screen
        log_file="/tmp/${session_name}.log"
        wrapped_cmd="$CMD > $log_file 2>&1; echo 'MJPG-Streamer exited. Consult $log_file'; sleep 3"
        screen -dmS "$session_name" bash -c "$wrapped_cmd"
        
        echo "    Started in screen: $session_name (Logs: $log_file)"
        echo "    Stream URL: http://$(hostname -I | awk '{print $1}'):$port/?action=stream"
    else
        echo "--> Device $device not found. Skipping $cam_name."
    fi
    
    cam_index=$((cam_index + 1))
done

echo ""
echo "Done! Active MJPG-Streamer screens:"
screen -ls | grep mjpg_cam || echo "None."
echo ""
echo "To stop them, run: screen -ls | grep mjpg_cam | cut -d. -f1 | awk '{print \$1}' | xargs kill"
