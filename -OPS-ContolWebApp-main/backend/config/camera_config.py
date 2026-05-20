"""Camera configuration for OPS Control Web App.

To add a camera: copy an existing block and increment the number.
To disable a camera: set "enabled": False.
"""

# ── Network ────────────────────────────────────────────────────────────────────
ROBOT_IP        = "192.168.2.50"   # IP of the robot (camera source)
CAM_RECEIVER_IP = "192.168.2.42"   # IP of the operator station (stream destination)

# ── Streaming defaults ─────────────────────────────────────────────────────────
DEFAULT_RESOLUTION = "1280x720"
DEFAULT_FRAMERATE  = 30
WEB_RESOLUTION     = "640x480"
WEB_FRAMERATE      = 15

# ── Individual camera handles ──────────────────────────────────────────────────
CAMERA_1_HANDLE  = "/dev/video0"
CAMERA_2_HANDLE  = "/dev/video2"
CAMERA_3_HANDLE  = "/dev/video4"
CAMERA_4_HANDLE  = "/dev/video6"
CAMERA_5_HANDLE  = "/dev/video8"
CAMERA_6_HANDLE  = "/dev/video10"
CAMERA_7_HANDLE  = "/dev/video12"
CAMERA_8_HANDLE  = "/dev/video14"

# ── HTTP (mjpg-streamer) ports ─────────────────────────────────────────────────
CAMERA_1_HTTP_PORT = 8081
CAMERA_2_HTTP_PORT = 8082
CAMERA_3_HTTP_PORT = 8083
CAMERA_4_HTTP_PORT = 8084
CAMERA_5_HTTP_PORT = 8085
CAMERA_6_HTTP_PORT = 8086
CAMERA_7_HTTP_PORT = 8087
CAMERA_8_HTTP_PORT = 8088

# ── UDP ports ──────────────────────────────────────────────────────────────────
CAMERA_1_UDP_PORT = 2140
CAMERA_2_UDP_PORT = 2141
CAMERA_3_UDP_PORT = 2142
CAMERA_4_UDP_PORT = 2143
CAMERA_5_UDP_PORT = 2144
CAMERA_6_UDP_PORT = 2145
CAMERA_7_UDP_PORT = 2146
CAMERA_8_UDP_PORT = 2147

# ── mjpg-streamer commands (run on robot) ──────────────────────────────────────
def _mjpg_cmd(device, port):
    return (
        f"mjpg_streamer "
        f"-i 'input_uvc.so -d {device} -r {WEB_RESOLUTION} -f {WEB_FRAMERATE} -y -q 50' "
        f"-o 'output_http.so -p {port}'"
    )

CAMERA_1_HTTP_CMD = _mjpg_cmd(CAMERA_1_HANDLE, CAMERA_1_HTTP_PORT)
CAMERA_2_HTTP_CMD = _mjpg_cmd(CAMERA_2_HANDLE, CAMERA_2_HTTP_PORT)
CAMERA_3_HTTP_CMD = _mjpg_cmd(CAMERA_3_HANDLE, CAMERA_3_HTTP_PORT)
CAMERA_4_HTTP_CMD = _mjpg_cmd(CAMERA_4_HANDLE, CAMERA_4_HTTP_PORT)
CAMERA_5_HTTP_CMD = _mjpg_cmd(CAMERA_5_HANDLE, CAMERA_5_HTTP_PORT)
CAMERA_6_HTTP_CMD = _mjpg_cmd(CAMERA_6_HANDLE, CAMERA_6_HTTP_PORT)
CAMERA_7_HTTP_CMD = _mjpg_cmd(CAMERA_7_HANDLE, CAMERA_7_HTTP_PORT)
CAMERA_8_HTTP_CMD = _mjpg_cmd(CAMERA_8_HANDLE, CAMERA_8_HTTP_PORT)

# ── GStreamer sender commands (run on robot via SSH) ───────────────────────────
def _gst_cmd(device, name, port):
    return (
        f'gst-launch-1.0 -e v4l2src device={device} '
        f'! image/jpeg,width=1280,height=720,framerate=30/1 '
        f'! jpegparse ! jpegdec ! videoconvert '
        f'! textoverlay text=\\"{name}\\" valignment=top halignment=left font-desc=\\"Sans, 18\\" '
        f'! x264enc tune=zerolatency bitrate=1000 speed-preset=superfast '
        f'! rtph264pay ! udpsink host={CAM_RECEIVER_IP} port={port}'
    )

CAMERA_1_CMD = _gst_cmd(CAMERA_1_HANDLE, "Kamera 1", CAMERA_1_UDP_PORT)
CAMERA_2_CMD = _gst_cmd(CAMERA_2_HANDLE, "Kamera 2", CAMERA_2_UDP_PORT)
CAMERA_3_CMD = _gst_cmd(CAMERA_3_HANDLE, "Kamera 3", CAMERA_3_UDP_PORT)
CAMERA_4_CMD = _gst_cmd(CAMERA_4_HANDLE, "Kamera 4", CAMERA_4_UDP_PORT)
CAMERA_5_CMD = _gst_cmd(CAMERA_5_HANDLE, "Kamera 5", CAMERA_5_UDP_PORT)
CAMERA_6_CMD = _gst_cmd(CAMERA_6_HANDLE, "Kamera 6", CAMERA_6_UDP_PORT)
CAMERA_7_CMD = _gst_cmd(CAMERA_7_HANDLE, "Kamera 7", CAMERA_7_UDP_PORT)
CAMERA_8_CMD = _gst_cmd(CAMERA_8_HANDLE, "Kamera 8", CAMERA_8_UDP_PORT)

# ── Camera list consumed by the backend API ────────────────────────────────────
# Set "enabled": False to hide a camera without removing its config.
CAMERAS = [
    {
        "id": "camera1", "name": "Kamera 1",
        "device": CAMERA_1_HANDLE,
        "http_port": CAMERA_1_HTTP_PORT, "udp_port": CAMERA_1_UDP_PORT,
        "url": f"http://{ROBOT_IP}:{CAMERA_1_HTTP_PORT}/?action=stream",
        "http_cmd": CAMERA_1_HTTP_CMD, "gst_cmd": CAMERA_1_CMD,
        "enabled": True, "type": "http_mjpeg",
    },
    {
        "id": "camera2", "name": "Kamera 2",
        "device": CAMERA_2_HANDLE,
        "http_port": CAMERA_2_HTTP_PORT, "udp_port": CAMERA_2_UDP_PORT,
        "url": f"http://{ROBOT_IP}:{CAMERA_2_HTTP_PORT}/?action=stream",
        "http_cmd": CAMERA_2_HTTP_CMD, "gst_cmd": CAMERA_2_CMD,
        "enabled": True, "type": "http_mjpeg",
    },
    {
        "id": "camera3", "name": "Kamera 3",
        "device": CAMERA_3_HANDLE,
        "http_port": CAMERA_3_HTTP_PORT, "udp_port": CAMERA_3_UDP_PORT,
        "url": f"http://{ROBOT_IP}:{CAMERA_3_HTTP_PORT}/?action=stream",
        "http_cmd": CAMERA_3_HTTP_CMD, "gst_cmd": CAMERA_3_CMD,
        "enabled": True, "type": "http_mjpeg",
    },
    {
        "id": "camera4", "name": "Kamera 4",
        "device": CAMERA_4_HANDLE,
        "http_port": CAMERA_4_HTTP_PORT, "udp_port": CAMERA_4_UDP_PORT,
        "url": f"http://{ROBOT_IP}:{CAMERA_4_HTTP_PORT}/?action=stream",
        "http_cmd": CAMERA_4_HTTP_CMD, "gst_cmd": CAMERA_4_CMD,
        "enabled": True, "type": "http_mjpeg",
    },
    {
        "id": "camera5", "name": "Kamera 5",
        "device": CAMERA_5_HANDLE,
        "http_port": CAMERA_5_HTTP_PORT, "udp_port": CAMERA_5_UDP_PORT,
        "url": f"http://{ROBOT_IP}:{CAMERA_5_HTTP_PORT}/?action=stream",
        "http_cmd": CAMERA_5_HTTP_CMD, "gst_cmd": CAMERA_5_CMD,
        "enabled": False, "type": "http_mjpeg",
    },
    {
        "id": "camera6", "name": "Kamera 6",
        "device": CAMERA_6_HANDLE,
        "http_port": CAMERA_6_HTTP_PORT, "udp_port": CAMERA_6_UDP_PORT,
        "url": f"http://{ROBOT_IP}:{CAMERA_6_HTTP_PORT}/?action=stream",
        "http_cmd": CAMERA_6_HTTP_CMD, "gst_cmd": CAMERA_6_CMD,
        "enabled": False, "type": "http_mjpeg",
    },
    {
        "id": "camera7", "name": "Kamera 7",
        "device": CAMERA_7_HANDLE,
        "http_port": CAMERA_7_HTTP_PORT, "udp_port": CAMERA_7_UDP_PORT,
        "url": f"http://{ROBOT_IP}:{CAMERA_7_HTTP_PORT}/?action=stream",
        "http_cmd": CAMERA_7_HTTP_CMD, "gst_cmd": CAMERA_7_CMD,
        "enabled": False, "type": "http_mjpeg",
    },
    {
        "id": "camera8", "name": "Kamera 8",
        "device": CAMERA_8_HANDLE,
        "http_port": CAMERA_8_HTTP_PORT, "udp_port": CAMERA_8_UDP_PORT,
        "url": f"http://{ROBOT_IP}:{CAMERA_8_HTTP_PORT}/?action=stream",
        "http_cmd": CAMERA_8_HTTP_CMD, "gst_cmd": CAMERA_8_CMD,
        "enabled": False, "type": "http_mjpeg",
    },
    {
        "id": "gst_camera1", "name": "Kamera 1 (GStreamer)",
        "device": CAMERA_1_HANDLE, "udp_port": CAMERA_1_UDP_PORT,
        "url": f"udp://{CAM_RECEIVER_IP}:{CAMERA_1_UDP_PORT}",
        "gst_cmd": CAMERA_1_CMD,
        "enabled": True, "type": "gstreamer",
    },
    {
        "id": "gst_camera2", "name": "Kamera 2 (GStreamer)",
        "device": CAMERA_2_HANDLE, "udp_port": CAMERA_2_UDP_PORT,
        "url": f"udp://{CAM_RECEIVER_IP}:{CAMERA_2_UDP_PORT}",
        "gst_cmd": CAMERA_2_CMD,
        "enabled": True, "type": "gstreamer",
    },
    {
        "id": "gst_camera3", "name": "Kamera 3 (GStreamer)",
        "device": CAMERA_3_HANDLE, "udp_port": CAMERA_3_UDP_PORT,
        "url": f"udp://{CAM_RECEIVER_IP}:{CAMERA_3_UDP_PORT}",
        "gst_cmd": CAMERA_3_CMD,
        "enabled": True, "type": "gstreamer",
    },
    {
        "id": "gst_camera4", "name": "Kamera 4 (GStreamer)",
        "device": CAMERA_4_HANDLE, "udp_port": CAMERA_4_UDP_PORT,
        "url": f"udp://{CAM_RECEIVER_IP}:{CAMERA_4_UDP_PORT}",
        "gst_cmd": CAMERA_4_CMD,
        "enabled": True, "type": "gstreamer",
    },
    {
        "id": "gst_camera5", "name": "Kamera 5 (GStreamer)",
        "device": CAMERA_5_HANDLE, "udp_port": CAMERA_5_UDP_PORT,
        "url": f"udp://{CAM_RECEIVER_IP}:{CAMERA_5_UDP_PORT}",
        "gst_cmd": CAMERA_5_CMD,
        "enabled": False, "type": "gstreamer",
    },
    {
        "id": "gst_camera6", "name": "Kamera 6 (GStreamer)",
        "device": CAMERA_6_HANDLE, "udp_port": CAMERA_6_UDP_PORT,
        "url": f"udp://{CAM_RECEIVER_IP}:{CAMERA_6_UDP_PORT}",
        "gst_cmd": CAMERA_6_CMD,
        "enabled": False, "type": "gstreamer",
    },
    {
        "id": "gst_camera7", "name": "Kamera 7 (GStreamer)",
        "device": CAMERA_7_HANDLE, "udp_port": CAMERA_7_UDP_PORT,
        "url": f"udp://{CAM_RECEIVER_IP}:{CAMERA_7_UDP_PORT}",
        "gst_cmd": CAMERA_7_CMD,
        "enabled": False, "type": "gstreamer",
    },
    {
        "id": "gst_camera8", "name": "Kamera 8 (GStreamer)",
        "device": CAMERA_8_HANDLE, "udp_port": CAMERA_8_UDP_PORT,
        "url": f"udp://{CAM_RECEIVER_IP}:{CAMERA_8_UDP_PORT}",
        "gst_cmd": CAMERA_8_CMD,
        "enabled": False, "type": "gstreamer",
    },
]
