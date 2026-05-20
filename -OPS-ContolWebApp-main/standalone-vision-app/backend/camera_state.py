import logging
import re
import subprocess
from copy import deepcopy

from pydantic import BaseModel


ZOOM_FACTORS = {
    "1x": 1.0,
    "1.5x": 1.5,
    "2x": 2.0,
    "3x": 3.0,
}

DEFAULT_ZOOM = "1x"
DEFAULT_EXECUTION_MODE = "local"
EXECUTION_MODES = ("local", "ssh")
DEFAULT_SSH_HOST = "192.168.2.50"
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "lrt_geeokom"
DEFAULT_SSH_PASSWORD = "qwerty"
DEFAULT_TARGET_PORT_BASE = 2140

logger = logging.getLogger(__name__)


DEFAULT_CAMERA_CONFIGS = {
    "1": {
        "device": "/dev/video0",
        "width": 1280,
        "height": 720,
        "framerate": 24,
        "bitrate": 512,
        "zoom": DEFAULT_ZOOM,
        "mirror_horizontal": False,
        "rotation": 0,
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "ssh_host": DEFAULT_SSH_HOST,
        "ssh_port": DEFAULT_SSH_PORT,
        "ssh_user": DEFAULT_SSH_USER,
        "ssh_password": DEFAULT_SSH_PASSWORD,
        "crop_top": 0,
        "crop_bottom": 0,
        "crop_left": 0,
        "crop_right": 0,
        "target_ip": "127.0.0.1",
        "target_port": 2140,
        "sender_running": False,
        "receiver_running": False,
    },
    "2": {
        "device": "/dev/video1",
        "width": 1280,
        "height": 720,
        "framerate": 24,
        "bitrate": 512,
        "zoom": DEFAULT_ZOOM,
        "mirror_horizontal": False,
        "rotation": 0,
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "ssh_host": DEFAULT_SSH_HOST,
        "ssh_port": DEFAULT_SSH_PORT,
        "ssh_user": DEFAULT_SSH_USER,
        "ssh_password": DEFAULT_SSH_PASSWORD,
        "crop_top": 0,
        "crop_bottom": 0,
        "crop_left": 0,
        "crop_right": 0,
        "target_ip": "127.0.0.1",
        "target_port": 2141,
        "sender_running": False,
        "receiver_running": False,
    },
    "3": {
        "device": "/dev/video2",
        "width": 1280,
        "height": 720,
        "framerate": 24,
        "bitrate": 512,
        "zoom": DEFAULT_ZOOM,
        "mirror_horizontal": False,
        "rotation": 0,
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "ssh_host": DEFAULT_SSH_HOST,
        "ssh_port": DEFAULT_SSH_PORT,
        "ssh_user": DEFAULT_SSH_USER,
        "ssh_password": DEFAULT_SSH_PASSWORD,
        "crop_top": 0,
        "crop_bottom": 0,
        "crop_left": 0,
        "crop_right": 0,
        "target_ip": "127.0.0.1",
        "target_port": 2142,
        "sender_running": False,
        "receiver_running": False,
    },
    "4": {
        "device": "/dev/video3",
        "width": 1280,
        "height": 720,
        "framerate": 24,
        "bitrate": 512,
        "zoom": DEFAULT_ZOOM,
        "mirror_horizontal": False,
        "rotation": 0,
        "execution_mode": DEFAULT_EXECUTION_MODE,
        "ssh_host": DEFAULT_SSH_HOST,
        "ssh_port": DEFAULT_SSH_PORT,
        "ssh_user": DEFAULT_SSH_USER,
        "ssh_password": DEFAULT_SSH_PASSWORD,
        "crop_top": 0,
        "crop_bottom": 0,
        "crop_left": 0,
        "crop_right": 0,
        "target_ip": "127.0.0.1",
        "target_port": 2143,
        "sender_running": False,
        "receiver_running": False,
    },
}


def _run_command(command):
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", "command not found"


def detect_preferred_encoder():
    # Prefer x264 for software encoding latency/compatibility.
    for encoder in ("x264enc", "openh264enc", "avenc_h264"):
        code, _stdout, _stderr = _run_command(["gst-inspect-1.0", encoder])
        if code == 0:
            return encoder
    return "x264enc"


PREFERRED_ENCODER = detect_preferred_encoder()


def list_video_devices():
    code, stdout, stderr = _run_command(["v4l2-ctl", "--list-devices"])
    if code != 0:
        logger.warning("v4l2-ctl --list-devices failed: %s", stderr.strip())
        return []

    devices = []
    current_name = "Unknown Camera"
    device_pattern = re.compile(r"^\s*(/dev/video\d+)\s*$")

    for line in stdout.splitlines():
        if not line.strip():
            continue
        if not line.startswith("\t") and line.endswith(":"):
            current_name = line[:-1].strip()
            continue

        match = device_pattern.match(line)
        if match:
            devices.append({"name": current_name, "device": match.group(1)})

    # Deduplicate while preserving order.
    seen = set()
    unique_devices = []
    for item in devices:
        dev = item["device"]
        if dev in seen:
            continue
        seen.add(dev)
        unique_devices.append(item)
    return unique_devices


def _sorted_modes(modes_map):
    modes = []
    for (width, height), fps_values in modes_map.items():
        fps_list = sorted(int(v) for v in fps_values)
        modes.append(
            {
                "width": int(width),
                "height": int(height),
                "framerates": fps_list,
            }
        )
    modes.sort(key=lambda mode: (mode["width"] * mode["height"], mode["width"], mode["height"]), reverse=True)
    return modes


def query_device_capabilities(device):
    code, stdout, stderr = _run_command(["v4l2-ctl", "--list-formats-ext", "--device", device])
    if code != 0:
        logger.warning("v4l2-ctl --list-formats-ext failed for %s: %s", device, stderr.strip())
        return {
            "supported_modes": [],
            "supported_resolutions": [],
            "supported_framerates": [],
        }

    size_pattern = re.compile(r"Size:\s+Discrete\s+(\d+)x(\d+)")
    fps_pattern = re.compile(r"\((\d+(?:\.\d+)?)\s+fps\)")

    current_size = None
    modes_map = {}

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        size_match = size_pattern.search(line)
        if size_match:
            width = int(size_match.group(1))
            height = int(size_match.group(2))
            current_size = (width, height)
            modes_map.setdefault(current_size, set())
            continue

        if current_size is None:
            continue

        fps_match = fps_pattern.search(line)
        if fps_match:
            fps_float = float(fps_match.group(1))
            fps_int = max(1, int(round(fps_float)))
            modes_map[current_size].add(fps_int)

    modes = _sorted_modes(modes_map)
    supported_framerates = sorted({fps for mode in modes for fps in mode["framerates"]})
    supported_resolutions = [
        {"width": mode["width"], "height": mode["height"]}
        for mode in modes
    ]

    return {
        "supported_modes": modes,
        "supported_resolutions": supported_resolutions,
        "supported_framerates": supported_framerates,
    }


def _choose_best_mode(supported_modes):
    if not supported_modes:
        return 1280, 720, 24

    preferred_width, preferred_height, preferred_fps = 1280, 720, 24

    def mode_score(mode):
        # Prefer 720p-ish modes with an FPS close to 24.
        area_distance = abs((mode["width"] * mode["height"]) - (preferred_width * preferred_height))
        size_distance = abs(mode["width"] - preferred_width) + abs(mode["height"] - preferred_height)
        fps_values = mode.get("framerates") or [preferred_fps]
        fps_distance = min(abs(fps - preferred_fps) for fps in fps_values)
        return area_distance, size_distance, fps_distance

    best_mode = min(supported_modes, key=mode_score)
    fps_values = best_mode.get("framerates") or [preferred_fps]
    best_fps = min(fps_values, key=lambda fps: abs(fps - preferred_fps))
    return int(best_mode["width"]), int(best_mode["height"]), int(best_fps)


def autodetect_camera_configs():
    devices = list_video_devices()
    if not devices:
        return None

    preferred_encoder = PREFERRED_ENCODER
    detected_configs = {}

    for index, info in enumerate(devices, start=1):
        capabilities = query_device_capabilities(info["device"])
        width, height, framerate = _choose_best_mode(capabilities["supported_modes"])
        cam_id = str(index)
        detected_configs[cam_id] = {
            "device": info["device"],
            "camera_name": info["name"],
            "width": width,
            "height": height,
            "framerate": framerate,
            "bitrate": 512,
            "encoder": preferred_encoder,
            "zoom": DEFAULT_ZOOM,
            "mirror_horizontal": False,
            "rotation": 0,
            "execution_mode": DEFAULT_EXECUTION_MODE,
            "ssh_host": DEFAULT_SSH_HOST,
            "ssh_port": DEFAULT_SSH_PORT,
            "ssh_user": DEFAULT_SSH_USER,
            "ssh_password": DEFAULT_SSH_PASSWORD,
            "crop_top": 0,
            "crop_bottom": 0,
            "crop_left": 0,
            "crop_right": 0,
            "target_ip": "127.0.0.1",
            "target_port": DEFAULT_TARGET_PORT_BASE + (index - 1),
            "sender_running": False,
            "receiver_running": False,
            "supported_modes": capabilities["supported_modes"],
            "supported_resolutions": capabilities["supported_resolutions"],
            "supported_framerates": capabilities["supported_framerates"],
        }
    return detected_configs


def normalize_zoom(zoom_value):
    if zoom_value is None:
        return DEFAULT_ZOOM

    if isinstance(zoom_value, (int, float)):
        target = float(zoom_value)
        for label, factor in ZOOM_FACTORS.items():
            if abs(factor - target) < 0.001:
                return label
        return DEFAULT_ZOOM

    zoom_text = str(zoom_value).strip()
    if zoom_text in ZOOM_FACTORS:
        return zoom_text

    try:
        target = float(zoom_text.rstrip("xX"))
    except ValueError:
        return DEFAULT_ZOOM

    for label, factor in ZOOM_FACTORS.items():
        if abs(factor - target) < 0.001:
            return label
    return DEFAULT_ZOOM


def apply_zoom_crop(config):
    width = max(1, int(config.get("width", 1280)))
    height = max(1, int(config.get("height", 720)))
    zoom_label = normalize_zoom(config.get("zoom"))
    zoom_factor = ZOOM_FACTORS[zoom_label]

    cropped_width = max(1, int(width / zoom_factor))
    cropped_height = max(1, int(height / zoom_factor))

    crop_left = max(0, (width - cropped_width) // 2)
    crop_right = max(0, width - cropped_width - crop_left)
    crop_top = max(0, (height - cropped_height) // 2)
    crop_bottom = max(0, height - cropped_height - crop_top)

    config["zoom"] = zoom_label
    config["crop_left"] = crop_left
    config["crop_right"] = crop_right
    config["crop_top"] = crop_top
    config["crop_bottom"] = crop_bottom
    return config


def normalize_camera_config(config):
    config["width"] = max(1, int(config.get("width", 1280)))
    config["height"] = max(1, int(config.get("height", 720)))
    config["framerate"] = max(1, int(config.get("framerate", 24)))
    config["bitrate"] = max(1, int(config.get("bitrate", 512)))
    config["encoder"] = str(config.get("encoder", PREFERRED_ENCODER)).strip() or PREFERRED_ENCODER
    config["mirror_horizontal"] = bool(config.get("mirror_horizontal", False))
    try:
        rotation = int(config.get("rotation", 0))
    except (ValueError, TypeError):
        rotation = 0
    if rotation not in (0, 90, 180, 270):
        rotation = 0
    config["rotation"] = rotation
    execution_mode = str(config.get("execution_mode", DEFAULT_EXECUTION_MODE)).strip().lower()
    if execution_mode not in EXECUTION_MODES:
        execution_mode = DEFAULT_EXECUTION_MODE
    config["execution_mode"] = execution_mode
    config["ssh_host"] = str(config.get("ssh_host", DEFAULT_SSH_HOST)).strip() or DEFAULT_SSH_HOST
    config["ssh_port"] = int(config.get("ssh_port", DEFAULT_SSH_PORT) or DEFAULT_SSH_PORT)
    config["ssh_user"] = str(config.get("ssh_user", DEFAULT_SSH_USER)).strip() or DEFAULT_SSH_USER
    config["ssh_password"] = str(config.get("ssh_password", DEFAULT_SSH_PASSWORD))

    # Keep user selections valid against probed capabilities when available.
    supported_modes = config.get("supported_modes") or []
    if supported_modes:
        matching_mode = None
        for mode in supported_modes:
            if int(mode.get("width", 0)) == config["width"] and int(mode.get("height", 0)) == config["height"]:
                matching_mode = mode
                break

        if matching_mode is None:
            matching_mode = min(
                supported_modes,
                key=lambda mode: abs(int(mode.get("width", 0)) - config["width"]) + abs(int(mode.get("height", 0)) - config["height"]),
            )
            config["width"] = int(matching_mode.get("width", config["width"]))
            config["height"] = int(matching_mode.get("height", config["height"]))

        mode_fps_values = [int(v) for v in (matching_mode.get("framerates") or []) if int(v) > 0]
        if mode_fps_values and config["framerate"] not in mode_fps_values:
            config["framerate"] = min(mode_fps_values, key=lambda fps: abs(fps - config["framerate"]))

    return apply_zoom_crop(config)


def build_camera_configs():
    detected_configs = autodetect_camera_configs()
    configs = detected_configs if detected_configs else deepcopy(DEFAULT_CAMERA_CONFIGS)
    for config in configs.values():
        normalize_camera_config(config)
    return configs


class CameraUpdate(BaseModel):
    width: int | None = None
    height: int | None = None
    framerate: int | None = None
    bitrate: int | None = None
    encoder: str | None = None
    zoom: str | None = None
    mirror_horizontal: bool | None = None
    rotation: int | None = None
    execution_mode: str | None = None
    ssh_host: str | None = None
    ssh_port: int | None = None
    ssh_user: str | None = None
    ssh_password: str | None = None
    crop_top: int | None = None
    crop_bottom: int | None = None
    crop_left: int | None = None
    crop_right: int | None = None
    target_ip: str | None = None
    target_port: int | None = None