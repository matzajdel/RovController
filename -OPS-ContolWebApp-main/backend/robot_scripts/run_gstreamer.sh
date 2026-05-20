#!/bin/bash

# Default Receiver IP (Operator's PC)
RECEIVER_IP="192.168.2.42"

# Parse arguments
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --ip) RECEIVER_IP="$2"; shift ;;
        *) echo "Unknown parameter passed: $1"; exit 1 ;;
    esac
    shift
done

echo "==================================================="
echo "Starting GStreamer Video Streams to IP: $RECEIVER_IP"
echo "==================================================="

# Default ports matches camera_config.py
PORTS=(6123 7123 8123 9123)
# We test these video hubs (usually cameras end up on these on Jetson)
DEVICES=("/dev/video0" "/dev/video2" "/dev/video4" "/dev/video6")

# Ensure screen is installed
if ! command -v screen &> /dev/null; then
    echo "Error: 'screen' is not installed. Please install it with: sudo apt install screen"
    exit 1
fi

cam_index=0
for device in "${DEVICES[@]}"; do
    cam_num=$((cam_index + 1))
    port=${PORTS[$cam_index]}
    cam_name="Kamera $cam_num"
    session_name="gst_cam$cam_num"
    
    if [ -e "$device" ]; then
        echo "--> Found device $device. Configuring $cam_name on port $port..."
        
        # Kill existing screen if any
        screen -S "$session_name" -X quit 2>/dev/null
        sleep 0.5
        
        # Try probing format
        FORMAT=$(v4l2-ctl --device="$device" --list-formats-ext 2>/dev/null)
        
        if echo "$FORMAT" | grep -q "MJPG"; then
            echo "    Format: MJPG detected."
            GST_CMD="gst-launch-1.0 -e v4l2src device=$device ! image/jpeg,width=1280,height=720,framerate=30/1 ! jpegparse ! jpegdec ! videoconvert ! textoverlay text=\"$cam_name\" valignment=top halignment=left font-desc=\"Sans, 18\" ! x264enc tune=zerolatency bitrate=1000 speed-preset=superfast ! rtph264pay ! udpsink host=$RECEIVER_IP port=$port"
        elif echo "$FORMAT" | grep -q "YUYV"; then
            echo "    Format: YUYV detected."
            GST_CMD="gst-launch-1.0 -e v4l2src device=$device ! video/x-raw,format=YUY2 ! videoconvert ! textoverlay text=\"$cam_name\" valignment=top halignment=left font-desc=\"Sans, 18\" ! x264enc tune=zerolatency bitrate=1000 speed-preset=superfast ! rtph264pay ! udpsink host=$RECEIVER_IP port=$port"
        else
            echo "    Warning: Unknown format. Falling back to MJPG pipeline."
            GST_CMD="gst-launch-1.0 -e v4l2src device=$device ! image/jpeg,width=1280,height=720,framerate=30/1 ! jpegparse ! jpegdec ! videoconvert ! textoverlay text=\"$cam_name\" valignment=top halignment=left font-desc=\"Sans, 18\" ! x264enc tune=zerolatency bitrate=1000 speed-preset=superfast ! rtph264pay ! udpsink host=$RECEIVER_IP port=$port"
        fi
        
        # Start in screen
        log_file="/tmp/${session_name}.log"
        wrapped_cmd="$GST_CMD > $log_file 2>&1; echo 'GStreamer exited. Consult $log_file'; sleep 3"
        screen -dmS "$session_name" bash -c "$wrapped_cmd"
        
        echo "    Started in screen: $session_name (Logs: $log_file)"
    else
        echo "--> Device $device not found. Skipping $cam_name."
    fi
    
    cam_index=$((cam_index + 1))
done

echo ""
echo "Done! Active GStreamer screens:"
screen -ls | grep gst_cam || echo "None."
echo ""
echo "To stop them, run: screen -ls | grep gst_cam | cut -d. -f1 | awk '{print \$1}' | xargs kill"
