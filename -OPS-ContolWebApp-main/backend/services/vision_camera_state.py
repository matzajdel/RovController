import json
import logging
from copy import deepcopy
from pathlib import Path

from pydantic import BaseModel


logger = logging.getLogger(__name__)

CAMERA_CONFIG_PATH = Path(__file__).resolve().parents[2] / "frontend" / "src" / "Vision" / "cameras.json"


ZOOM_FACTORS = {
    "1x": 1.0,
    "1.5x": 1.5,
    "2x": 2.0,
    "3x": 3.0,
}

RESOLUTION_PRESETS = {
    "Full HD (1920x1080)": {"width": 1920, "height": 1080},
    "HD (1280x720)": {"width": 1280, "height": 720},
    "qHD (960x540)": {"width": 960, "height": 540},
    "VGA (640x480)": {"width": 640, "height": 480},
    "SD Wide (854x480)": {"width": 854, "height": 480},
    "nHD (640x360)": {"width": 640, "height": 360},
    "QVGA Wide (426x240)": {"width": 426, "height": 240},
}

DEFAULT_ZOOM = "1x"
DEFAULT_EXECUTION_MODE = "ssh"
DEFAULT_SOURCE_FORMAT = "auto"
EXECUTION_MODES = ("local", "ssh")
SOURCE_FORMAT_MODES = ("auto", "h264", "mjpeg", "yuy2", "raw")
DEFAULT_SSH_HOST = "192.168.2.50"
DEFAULT_SSH_PORT = 22
DEFAULT_SSH_USER = "lrt_geeokom"
DEFAULT_SSH_PASSWORD = "qwerty"


# Devices match camera_config.py CAMERA_DEFINITIONS (even-numbered V4L2 nodes).
# To add more default camera slots, append entries here.
_CAMERA_DEVICES = [
    "/dev/video0",
    "/dev/video2",
    "/dev/video4",
    "/dev/video6",
    "/dev/video8",
    "/dev/video10",
    "/dev/video12",
    "/dev/video14",
]

# Build default camera slots from the full known device list.
# This removes the old fixed 4-camera cap while still allowing additional
# camera IDs loaded from cameras.json (which can exceed this list).
NUM_CAMERAS = len(_CAMERA_DEVICES)

DEFAULT_CAMERA_CONFIGS = {
    str(n): {
        "device": _CAMERA_DEVICES[n - 1],
        "width": 1280,
        "height": 720,
        "framerate": 24,
        "bitrate": 512,
        "zoom": DEFAULT_ZOOM,
        "mirror_horizontal": False,
        "rotation": 0,
        "source_format": DEFAULT_SOURCE_FORMAT,
        "force_software_transcode": True,
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
        "target_port": 2139 + n,
        "sender_running": False,
        "receiver_running": False,
    }
    for n in range(1, NUM_CAMERAS + 1)
}


def _camera_sort_key(cam_id: str) -> tuple[int, str]:
    try:
        return (int(str(cam_id)), str(cam_id))
    except (TypeError, ValueError):
        return (10**9, str(cam_id))


def _default_camera_config_for(cam_id: str, fallback_index: int) -> dict:
    try:
        numeric_id = int(str(cam_id))
    except (TypeError, ValueError):
        numeric_id = fallback_index

    index = max(1, numeric_id)
    device_idx = index - 1
    if 0 <= device_idx < len(_CAMERA_DEVICES):
        device = _CAMERA_DEVICES[device_idx]
    else:
        # Continue the existing even-node convention when outside predefined list.
        device = f"/dev/video{device_idx * 2}"

    return {
        "device": device,
        "width": 1280,
        "height": 720,
        "framerate": 24,
        "bitrate": 512,
        "zoom": DEFAULT_ZOOM,
        "mirror_horizontal": False,
        "rotation": 0,
        "source_format": DEFAULT_SOURCE_FORMAT,
        "force_software_transcode": True,
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
        "target_port": 2139 + index,
        "sender_running": False,
        "receiver_running": False,
    }


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

    # x264/H264 pipelines are more stable with even frame dimensions.
    # For 1.5x on 1280x720 this prevents odd width (853) negotiation failures.
    if cropped_width > 1 and cropped_width % 2 != 0:
        cropped_width -= 1
    if cropped_height > 1 and cropped_height % 2 != 0:
        cropped_height -= 1

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
    config["mirror_horizontal"] = bool(config.get("mirror_horizontal", False))
    try:
        rotation = int(config.get("rotation", 0))
    except (ValueError, TypeError):
        rotation = 0
    if rotation not in (0, 90, 180, 270):
        rotation = 0
    config["rotation"] = rotation
    source_format = str(config.get("source_format", DEFAULT_SOURCE_FORMAT)).strip().lower()
    if source_format not in SOURCE_FORMAT_MODES:
        source_format = DEFAULT_SOURCE_FORMAT
    config["source_format"] = source_format
    config["force_software_transcode"] = bool(config.get("force_software_transcode", True))
    execution_mode = str(config.get("execution_mode", DEFAULT_EXECUTION_MODE)).strip().lower()
    if execution_mode not in EXECUTION_MODES:
        execution_mode = DEFAULT_EXECUTION_MODE
    config["execution_mode"] = execution_mode
    config["ssh_host"] = str(config.get("ssh_host", DEFAULT_SSH_HOST)).strip() or DEFAULT_SSH_HOST
    config["ssh_port"] = int(config.get("ssh_port", DEFAULT_SSH_PORT) or DEFAULT_SSH_PORT)
    config["ssh_user"] = str(config.get("ssh_user", DEFAULT_SSH_USER)).strip() or DEFAULT_SSH_USER
    config["ssh_password"] = str(config.get("ssh_password", DEFAULT_SSH_PASSWORD))
    config["sender_running"] = bool(config.get("sender_running", False))
    config["receiver_running"] = bool(config.get("receiver_running", False))
    return apply_zoom_crop(config)


def build_camera_configs(overrides=None):
    if isinstance(overrides, dict) and overrides:
        configs = {}
        ordered_ids = sorted([str(cam_id) for cam_id in overrides.keys()], key=_camera_sort_key)
        for fallback_index, cam_id in enumerate(ordered_ids, start=1):
            base = _default_camera_config_for(cam_id, fallback_index)
            override = overrides.get(cam_id)
            if isinstance(override, dict):
                base.update(override)
            configs[cam_id] = base
    else:
        configs = deepcopy(DEFAULT_CAMERA_CONFIGS)

    for config in configs.values():
        normalize_camera_config(config)
    return configs


def load_camera_configs():
    overrides = None
    if CAMERA_CONFIG_PATH.exists():
        try:
            overrides = json.loads(CAMERA_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load camera config from %s: %s", CAMERA_CONFIG_PATH, exc)
    return build_camera_configs(overrides)


def save_camera_configs(configs):
    normalized_configs = build_camera_configs(configs)
    CAMERA_CONFIG_PATH.write_text(
        json.dumps(normalized_configs, indent=2) + "\n",
        encoding="utf-8",
    )
    return normalized_configs


class CameraUpdate(BaseModel):
    device: str | None = None
    width: int | None = None
    height: int | None = None
    framerate: int | None = None
    bitrate: int | None = None
    zoom: str | None = None
    mirror_horizontal: bool | None = None
    rotation: int | None = None
    source_format: str | None = None
    force_software_transcode: bool | None = None
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
