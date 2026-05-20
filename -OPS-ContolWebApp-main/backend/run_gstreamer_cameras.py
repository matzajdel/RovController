#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import time

# Add backend dir to python path so we can import config
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from config.camera_config import CAMERA_1_UDP_PORT, CAMERA_2_UDP_PORT, CAMERA_3_UDP_PORT, CAMERA_4_UDP_PORT, CAM_RECEIVER_IP
import json

# Try to load receiver IP from dynamic config
RECEIVER_IP = CAM_RECEIVER_IP
config_path = os.path.join(script_dir, "config", "remote_cameras.json")
if os.path.exists(config_path):
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
            if 'receiver_ip' in config:
                RECEIVER_IP = config['receiver_ip']
    except Exception as e:
        print(f"Error reading config: {e}")


def generate_gst_command(device_handle, receiver_ip, udp_port, camera_name):
    print(f"  Probing device {device_handle} for formats...")
    try:
        # Run v4l2-ctl to get formats
        result = subprocess.run(f"v4l2-ctl --device={device_handle} --list-formats-ext", shell=True, capture_output=True, text=True)
        out = result.stdout
        
        # Check available formats in order of preference
        if "MJPG" in out:
            print("  -> Found MJPG format support. Using MJPG pipeline.")
            return f"gst-launch-1.0 -e v4l2src device={device_handle} ! image/jpeg,width=1280,height=720,framerate=30/1 ! jpegparse ! jpegdec ! videoconvert ! textoverlay text=\\\"{camera_name}\\\" valignment=top halignment=left font-desc=\\\"Sans, 18\\\" ! x264enc tune=zerolatency bitrate=1000 speed-preset=superfast ! rtph264pay ! udpsink host={receiver_ip} port={udp_port}"
        elif "YUYV" in out:
            print("  -> Found YUYV format support. Using YUYV pipeline.")
            return f"gst-launch-1.0 -e v4l2src device={device_handle} ! video/x-raw,format=YUY2 ! videoconvert ! textoverlay text=\\\"{camera_name}\\\" valignment=top halignment=left font-desc=\\\"Sans, 18\\\" ! x264enc tune=zerolatency bitrate=1000 speed-preset=superfast ! rtph264pay ! udpsink host={receiver_ip} port={udp_port}"
        elif "GREY" in out:
            print("  -> Found GREY format support. Using GREY pipeline.")
            return f"gst-launch-1.0 -e v4l2src device={device_handle} ! video/x-raw,format=GRAY8 ! videoconvert ! textoverlay text=\\\"{camera_name}\\\" valignment=top halignment=left font-desc=\\\"Sans, 18\\\" ! x264enc tune=zerolatency bitrate=1000 speed-preset=superfast ! rtph264pay ! udpsink host={receiver_ip} port={udp_port}"
        else:
            print("  -> WARNING: No known format detected. Falling back to default MJPG pipeline.")
            return f"gst-launch-1.0 -e v4l2src device={device_handle} ! image/jpeg,width=1280,height=720,framerate=30/1 ! jpegparse ! jpegdec ! videoconvert ! textoverlay text=\\\"{camera_name}\\\" valignment=top halignment=left font-desc=\\\"Sans, 18\\\" ! x264enc tune=zerolatency bitrate=1000 speed-preset=superfast ! rtph264pay ! udpsink host={receiver_ip} port={udp_port}"
    except Exception as e:
        print(f"  -> Error probing device: {e}. Falling back to default pipeline.")
        return f"gst-launch-1.0 -e v4l2src device={device_handle} ! image/jpeg,width=1280,height=720,framerate=30/1 ! jpegparse ! jpegdec ! videoconvert ! textoverlay text=\\\"{camera_name}\\\" valignment=top halignment=left font-desc=\\\"Sans, 18\\\" ! x264enc tune=zerolatency bitrate=1000 speed-preset=superfast ! rtph264pay ! udpsink host={receiver_ip} port={udp_port}"

def run_in_screen(session_name, cmd):
    # Kill existing screen if any
    subprocess.run(f"screen -S {session_name} -X quit 2>/dev/null", shell=True)
    time.sleep(0.5)
    
    # Start new screen session wrapping command with logging and delay on exit
    log_file = f"/tmp/{session_name}.log"
    wrapped_cmd = f"{cmd} > {log_file} 2>&1; echo 'GStreamer exited. Consult {log_file}'; sleep 3"
    screen_cmd = f"screen -dmS {session_name} bash -c '{wrapped_cmd}'"
    
    print(f"Starting screen session '{session_name}' (Logs: {log_file})")
    subprocess.run(screen_cmd, shell=True)
    return session_name

def main():
    parser = argparse.ArgumentParser(description="Run GStreamer cameras in screen sessions.")
    parser.add_argument("--ip", type=str, default=RECEIVER_IP, help="Target IP address for UDP stream (default from config)")
    parser.add_argument("--cam1", type=str, default="/dev/video0", help="Video device for Camera 1 (e.g., /dev/video0)")
    parser.add_argument("--cam2", type=str, default="/dev/video2", help="Video device for Camera 2")
    parser.add_argument("--cam3", type=str, default="/dev/video4", help="Video device for Camera 3")
    parser.add_argument("--cam4", type=str, default="/dev/video6", help="Video device for Camera 4")
    parser.add_argument("--disable-cam2", action="store_true", help="Disable Camera 2")
    parser.add_argument("--disable-cam3", action="store_true", help="Disable Camera 3")
    parser.add_argument("--disable-cam4", action="store_true", help="Disable Camera 4")

    args = parser.parse_args()

    print("====================================")
    print(f"Starting GStreamer Camera Pipelines to {args.ip}")
    print("====================================")

    cameras_to_run = []
    
    cameras_to_run.append(("Kamera 1", args.cam1, args.ip, CAMERA_1_UDP_PORT, "gst_cam1"))
    
    if not args.disable_cam2:
        cameras_to_run.append(("Kamera 2", args.cam2, args.ip, CAMERA_2_UDP_PORT, "gst_cam2"))
    if not args.disable_cam3:
        cameras_to_run.append(("Kamera 3", args.cam3, args.ip, CAMERA_3_UDP_PORT, "gst_cam3"))
    if not args.disable_cam4:
        cameras_to_run.append(("Kamera 4", args.cam4, args.ip, CAMERA_4_UDP_PORT, "gst_cam4"))

    active_screens = []
    for name, device, ip, port, screen_name in cameras_to_run:
        print(f"\nConfiguring {name} on {device} to port {port}")
        cmd = generate_gst_command(device, ip, port, name)
        print(f"Command: {cmd}")
        run_in_screen(screen_name, cmd)
        active_screens.append(screen_name)

    print("\nAll enabled cameras started in screen sessions.")
    print("You can view them using: screen -r <session_name>")
    for s in active_screens:
        print(f"  - {s}")
    
    print("\nTo stop them, you can run this script with a kill modifier, or manually:")
    print("screen -ls | grep gst_cam | cut -d. -f1 | awk '{print $1}' | xargs kill")

if __name__ == "__main__":
    main()
