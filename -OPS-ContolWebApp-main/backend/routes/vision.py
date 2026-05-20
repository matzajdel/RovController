"""Vision/camera control endpoints for Mars rover."""
from __future__ import annotations

 

import asyncio
import base64
import json
import logging
import os
import re
import shlex
import subprocess
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Path, Query
from pydantic import BaseModel
from services.vision_camera_controller import camera_controller as standalone_camera_controller
from services.vision_camera_state import (
    CameraUpdate as StandaloneCameraUpdate,
    EXECUTION_MODES,
    RESOLUTION_PRESETS,
    SOURCE_FORMAT_MODES,
    ZOOM_FACTORS,
    load_camera_configs as load_standalone_camera_configs,
    normalize_camera_config as normalize_standalone_camera_config,
    save_camera_configs as save_standalone_camera_configs,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Store active camera streams
active_streams = {}
camera_metrics = {}


# Cache for SSH camera discovery to avoid repeated slow probes during UI refresh.
AUTO_DISCOVERY_CACHE = {
    "expires_at": 0.0,
    "cameras": [],
    "last_error": None,
    "last_probe_host": None,
    "last_probe": None,
}
AUTO_DISCOVERY_TTL_S = 15.0
V4L2_CAPS_TTL_S = 20.0
V4L2_CAPS_CACHE: dict[str, dict[str, object]] = {}


class CameraSettings(BaseModel):
    """Camera configuration settings."""
    resolution: str  # "320x240", "640x480", "1280x720"
    fps: int  # 5, 15, 30
    compression: str  # "raw", "compressed"
    jpeg_quality: int = 50  # 1-100
    zoom_preset: str = "none"  # "none", "1.5x", "2x", "3x"


def get_zoom_params(zoom_preset: str):
    """Convert zoom preset to ROI parameters (x, y, width, height)."""
    presets = {
        "none": (0.0, 0.0, 1.0, 1.0),
        "1.5x": (0.167, 0.167, 0.666, 0.666),  # Center crop for 1.5x zoom
        "2x": (0.25, 0.25, 0.5, 0.5),          # Center crop for 2x zoom
        "3x": (0.333, 0.333, 0.334, 0.334),    # Center crop for 3x zoom
    }
    return presets.get(zoom_preset, presets["none"])


def _extract_host_from_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    match = re.match(r"^[a-zA-Z]+://([^/:]+)", str(url))
    return match.group(1) if match else None


def _collect_known_devices(cameras: list[dict]) -> set[str]:
    devices = set()
    for camera in cameras:
        device = camera.get("device")
        if isinstance(device, str) and device.startswith("/dev/video"):
            devices.add(device)
    return devices


def _device_sort_key(device: str) -> tuple[int, str]:
    match = re.search(r"(\d+)$", device or "")
    if not match:
        return (10**9, device or "")
    return (int(match.group(1)), device)


def _build_autodiscovered_standalone_configs(
    existing_configs: dict[str, dict],
    discovered_devices: list[str],
) -> dict[str, dict]:
    if not discovered_devices:
        return existing_configs

    sorted_devices = sorted(set(discovered_devices), key=_device_sort_key)
    existing_by_device = {
        cfg.get("device"): cfg
        for cfg in existing_configs.values()
        if isinstance(cfg, dict) and isinstance(cfg.get("device"), str)
    }

    template = next(iter(existing_configs.values()), {})
    rebuilt: dict[str, dict] = {}

    for index, device in enumerate(sorted_devices, start=1):
        previous = existing_by_device.get(device, template)
        config = dict(previous) if isinstance(previous, dict) else {}
        config["device"] = device
        config.setdefault("target_port", 2139 + index)
        config["target_port"] = 2139 + index
        # Preserve running-state only when we already tracked this exact device.
        if device not in existing_by_device:
            config["sender_running"] = False
            config["receiver_running"] = False

        normalize_standalone_camera_config(config)
        rebuilt[str(index)] = config

    return rebuilt


def _next_camera_id(existing_configs: dict[str, dict]) -> str:
    numeric_ids = []
    for cam_id in existing_configs.keys():
        try:
            numeric_ids.append(int(str(cam_id)))
        except (TypeError, ValueError):
            continue
    return str(max(numeric_ids, default=0) + 1)


def _camera_id_sort_key(cam_id: str) -> tuple[int, str]:
    try:
        return (int(str(cam_id)), str(cam_id))
    except (TypeError, ValueError):
        return (10**9, str(cam_id))


def _ensure_unique_target_ports(configs: dict[str, dict], base_port: int = 2140) -> bool:
    """Ensure each camera uses a distinct UDP port for sender/listener pipelines."""
    changed = False
    used_ports: set[int] = set()

    ordered_ids = sorted([str(cam_id) for cam_id in configs.keys()], key=_camera_id_sort_key)
    for idx, cam_id in enumerate(ordered_ids):
        cfg = configs.get(cam_id)
        if not isinstance(cfg, dict):
            continue

        desired = base_port + idx
        try:
            candidate = int(cfg.get("target_port", desired))
        except (TypeError, ValueError):
            candidate = desired

        if candidate <= 0 or candidate in used_ports:
            candidate = desired
            while candidate in used_ports:
                candidate += 1

        if cfg.get("target_port") != candidate:
            cfg["target_port"] = candidate
            changed = True

        used_ports.add(candidate)

    return changed


def _consolidate_configs_by_groups(
    existing_configs: dict[str, dict],
    camera_groups: list[dict],
) -> None:
    """Rebuild configs so there is exactly one entry per physical camera.

    Preserves the user-selected device and all other settings for any camera
    that already had a config.  Newly discovered groups get a config seeded
    from the first video node in that group.
    """
    if not camera_groups:
        return

    # Map every known saved device -> its cam_id.
    existing_by_device: dict[str, str] = {
        str(cfg.get("device")): cam_id
        for cam_id, cfg in existing_configs.items()
        if isinstance(cfg, dict) and isinstance(cfg.get("device"), str)
    }

    consolidated: dict[str, dict] = {}
    used_ids: set[str] = set()

    for index, group in enumerate(camera_groups, start=1):
        group_nodes = [n for n in (group.get("nodes") or []) if isinstance(n, str)]
        if not group_nodes:
            continue

        # Find the first saved config whose device belongs to this group.
        existing_cfg: dict | None = None
        existing_id: str | None = None
        for node in group_nodes:
            saved_id = existing_by_device.get(node)
            if saved_id and saved_id in existing_configs:
                existing_cfg = dict(existing_configs[saved_id])
                existing_id = str(saved_id)
                break

        if existing_id and existing_id not in used_ids:
            cam_id = existing_id
        else:
            cam_id = _next_camera_id({**existing_configs, **consolidated})

        if existing_cfg is not None:
            cfg = existing_cfg
        else:
            template = next(iter(existing_configs.values()), {})
            cfg = dict(template) if isinstance(template, dict) else {}
            cfg["device"] = group_nodes[0]
            cfg["sender_running"] = False
            cfg["receiver_running"] = False

        if "target_port" not in cfg or not isinstance(cfg.get("target_port"), int):
            cfg["target_port"] = 2139 + index
        cfg["camera_name"] = group.get("name", f"Camera {index}")
        normalize_standalone_camera_config(cfg)
        consolidated[cam_id] = cfg
        used_ids.add(cam_id)

    existing_configs.clear()
    existing_configs.update(consolidated)


def _autodiscovery_diagnostics() -> dict[str, object]:
    last_probe = AUTO_DISCOVERY_CACHE.get("last_probe") or {}
    return {
        "last_probe_host": AUTO_DISCOVERY_CACHE.get("last_probe_host"),
        "last_error": AUTO_DISCOVERY_CACHE.get("last_error"),
        "last_count": len(AUTO_DISCOVERY_CACHE.get("cameras", [])),
        "last_probe_exit_code": last_probe.get("exit_code"),
        "last_probe_timed_out": bool(last_probe.get("timed_out", False)),
    }


def _resolve_discovery_ssh_target(cameras: list[dict]) -> dict[str, object]:
    ssh_host = (
        os.getenv("VISION_SSH_HOST")
        or os.getenv("ROBOT_IP")
        or _extract_host_from_url(next((c.get("url") for c in cameras if c.get("url")), None))
        or "192.168.2.50"
    )
    ssh_user = os.getenv("VISION_SSH_USER") or "lrt_geeokom"
    ssh_password = os.getenv("VISION_SSH_PASSWORD") or "qwerty"
    ssh_port = int(os.getenv("VISION_SSH_PORT") or "22")
    return {
        "ssh_host": ssh_host,
        "ssh_user": ssh_user,
        "ssh_password": ssh_password,
        "ssh_port": ssh_port,
    }


async def _run_remote_v4l2_probe(cameras: list[dict], timeout_s: int = 5) -> dict[str, object]:
    target = _resolve_discovery_ssh_target(cameras)
    ssh_host = str(target["ssh_host"])
    ssh_user = str(target["ssh_user"])
    ssh_password = str(target["ssh_password"])
    ssh_port = int(target["ssh_port"])

    remote_command = "v4l2-ctl --list-devices 2>&1 || v4l2-ctl --device-list 2>&1"
    command = [
        "sshpass", "-p", ssh_password,
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=3",
        "-p", str(ssh_port),
        f"{ssh_user}@{ssh_host}",
        "bash -lc " + shlex.quote(remote_command),
    ]

    probe_result: dict[str, object] = {
        "ssh_host": ssh_host,
        "ssh_user": ssh_user,
        "ssh_port": ssh_port,
        "remote_command": remote_command,
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "timed_out": False,
        "error": None,
    }

    try:
        result = await asyncio.to_thread(subprocess.run, command, capture_output=True, text=True, check=False, timeout=timeout_s)
        probe_result["stdout"] = result.stdout or ""
        probe_result["stderr"] = result.stderr or ""
        probe_result["exit_code"] = int(result.returncode)
    except FileNotFoundError:
        probe_result["error"] = "sshpass is not installed on backend host"
    except subprocess.TimeoutExpired:
        probe_result["timed_out"] = True
        probe_result["error"] = "SSH probe timed out"
    except Exception as exc:
        probe_result["error"] = str(exc)

    return probe_result


async def _discover_remote_v4l2_cameras(cameras: list[dict], include_known_devices: bool = False) -> list[dict]:
    now = time.monotonic()
    if now < float(AUTO_DISCOVERY_CACHE.get("expires_at", 0.0)):
        known_devices = _collect_known_devices(cameras)
        cached = list(AUTO_DISCOVERY_CACHE.get("cameras", []))
        if include_known_devices:
            return cached
        return [cam for cam in cached if cam.get("device") not in known_devices]

    target = _resolve_discovery_ssh_target(cameras)
    ssh_host = str(target["ssh_host"])
    AUTO_DISCOVERY_CACHE["last_probe_host"] = ssh_host
    AUTO_DISCOVERY_CACHE["last_error"] = None

    discovered: list[dict] = []
    known_devices = _collect_known_devices(cameras)
    probe_result = await _run_remote_v4l2_probe(cameras)
    AUTO_DISCOVERY_CACHE["last_probe"] = probe_result

    try:
        if probe_result.get("error"):
            AUTO_DISCOVERY_CACHE["last_error"] = str(probe_result["error"])
            AUTO_DISCOVERY_CACHE["expires_at"] = time.monotonic() + AUTO_DISCOVERY_TTL_S
            AUTO_DISCOVERY_CACHE["cameras"] = []
            return []

        output = f"{probe_result.get('stdout', '')}\n{probe_result.get('stderr', '')}"
        devices_with_names = _parse_v4l2_devices_with_names(output)
        # Only video nodes (not media nodes) for streaming selection.
        video_pairs = [(d, n, gidx) for d, n, gidx in devices_with_names if d.startswith("/dev/video")]
        camera_groups = _build_camera_groups(video_pairs)

        for group in camera_groups:
            nodes = group.get("nodes", [])
            if not nodes:
                continue
            
            # The first node is typically the capture device we want
            primary_device = nodes[0]
            
            if not include_known_devices and primary_device in known_devices:
                continue
                
            discovered.append({
                "id": f"v4l:{primary_device}",
                "name": f"{group.get('name', 'Unknown Camera')} ({primary_device})",
                "detected_name": group.get("base_name", "Unknown Camera"),
                "device": primary_device,
                "available": True,
                "type": "v4l2",
                "source": "ssh_auto_discovery",
                "camera_group": group.get("name", "Unknown Camera"),
                "camera_group_index": group.get("group_index", 0),
            })

        AUTO_DISCOVERY_CACHE["camera_groups"] = camera_groups

        if discovered:
            logger.info("Auto-discovered %d V4L2 cameras over SSH", len(discovered))
        else:
            AUTO_DISCOVERY_CACHE["last_error"] = (
                "No /dev/video* devices detected by remote v4l2-ctl"
            )
    except Exception as exc:
        AUTO_DISCOVERY_CACHE["last_error"] = str(exc)
        logger.info("Skipping camera auto-discovery due to probe error: %s", exc)

    AUTO_DISCOVERY_CACHE["expires_at"] = time.monotonic() + AUTO_DISCOVERY_TTL_S
    AUTO_DISCOVERY_CACHE["cameras"] = discovered
    return list(discovered)


def _parse_v4l2_devices_with_names(output: str) -> list[tuple[str, str, int]]:
    devices: list[tuple[str, str, int]] = []
    current_name = "Unknown Camera"
    current_group_index = 0
    for raw_line in (output or "").splitlines():
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith(":") and "/dev/video" not in stripped:
            current_name = stripped[:-1].strip() or "Unknown Camera"
            current_group_index += 1
            continue

        match = re.match(r"^\s*(/dev/video\d+)\s*$", line)
        if match:
            devices.append((match.group(1), current_name, current_group_index))
    return devices


def _build_camera_groups(devices_with_names: list[tuple[str, str, int]]) -> list[dict]:
    """Group /dev/video* nodes by their physical camera name.

    Returns a list like:
      [{"id": "camera-1", "name": "Runcam USB Camera", "nodes": ["/dev/video0", "/dev/video1"]}, ...]
    Only /dev/video* nodes are kept (media nodes filtered out).
    """
    grouped_by_occurrence: dict[int, dict] = {}
    order: list[int] = []
    for device, name, group_index in devices_with_names:
        if not device.startswith("/dev/video"):
            continue
        if group_index not in grouped_by_occurrence:
            grouped_by_occurrence[group_index] = {
                "base_name": name or "Unknown Camera",
                "nodes": [],
                "group_index": group_index,
            }
            order.append(group_index)
        grouped_by_occurrence[group_index]["nodes"].append(device)

    raw_groups = [grouped_by_occurrence[idx] for idx in order]
    totals_by_name: dict[str, int] = {}
    for group in raw_groups:
        base_name = str(group.get("base_name") or "Unknown Camera")
        totals_by_name[base_name] = totals_by_name.get(base_name, 0) + 1

    seen_by_name: dict[str, int] = {}
    unique_groups: list[dict] = []
    for group in raw_groups:
        base_name = str(group.get("base_name") or "Unknown Camera")
        seen_by_name[base_name] = seen_by_name.get(base_name, 0) + 1
        total = totals_by_name.get(base_name, 1)
        ordinal = seen_by_name[base_name]

        if total > 1:
            display_name = f"{base_name} #{ordinal}"
        else:
            display_name = base_name

        first_node = next((n for n in group.get("nodes", []) if isinstance(n, str)), "")
        node_suffix = first_node.replace("/dev/", "") if first_node else f"g{group.get('group_index', 0)}"
        group_id = f"camgrp:{node_suffix}"

        unique_groups.append({
            "id": group_id,
            "name": display_name,
            "base_name": base_name,
            "nodes": group.get("nodes", []),
            "ordinal": ordinal,
            "occurrences": total,
        })

    return unique_groups


def _parse_v4l2_source_modes(formats_output: str) -> list[str]:
    normalized = (formats_output or "").upper()
    modes = ["raw"]
    if "H264" in normalized or "X264" in normalized:
        modes.append("h264")
    if "MJPG" in normalized or "MJPEG" in normalized or "JPEG" in normalized:
        modes.append("mjpeg")
    if "YUYV" in normalized or "YUY2" in normalized:
        modes.append("yuy2")
    # Preserve stable order expected by UI.
    ordered = []
    for mode in ("raw", "h264", "mjpeg", "yuy2"):
        if mode in modes and mode not in ordered:
            ordered.append(mode)
    return ordered


async def _fetch_remote_v4l2_caps(device: str, config: dict | None = None) -> dict[str, object]:
    now = time.monotonic()
    cache_entry = V4L2_CAPS_CACHE.get(device)
    if cache_entry and now < float(cache_entry.get("expires_at", 0.0)):
        return dict(cache_entry.get("value", {}))

    target = _resolve_discovery_ssh_target([])
    if isinstance(config, dict):
        target["ssh_host"] = str(config.get("ssh_host") or target["ssh_host"])
        target["ssh_user"] = str(config.get("ssh_user") or target["ssh_user"])
        target["ssh_password"] = str(config.get("ssh_password") or target["ssh_password"])
        target["ssh_port"] = int(config.get("ssh_port") or target["ssh_port"])
    escaped_device = shlex.quote(device)
    remote_command = (
        f"v4l2-ctl --device={escaped_device} --all 2>/dev/null; "
        f"v4l2-ctl --device={escaped_device} --list-formats-ext 2>&1 "
        f"|| v4l2-ctl --device={escaped_device} --list-formats 2>&1"
    )
    command = [
        "sshpass", "-p", str(target["ssh_password"]),
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=3",
        "-p", str(target["ssh_port"]),
        f"{target['ssh_user']}@{target['ssh_host']}",
        "bash -lc " + shlex.quote(remote_command),
    ]

    result_payload: dict[str, object] = {
        "supported_source_formats": ["auto", "raw"],
        "v4l2_formats_output": "",
        "error": None,
    }

    try:
        result = await asyncio.to_thread(subprocess.run, command, capture_output=True, text=True, check=False, timeout=8)
        output = f"{result.stdout or ''}\n{result.stderr or ''}"
        modes = _parse_v4l2_source_modes(output)
        result_payload = {
            "supported_source_formats": ["auto", *modes],
            "v4l2_formats_output": output.strip(),
            "error": None if int(result.returncode) == 0 else f"v4l2-ctl exited with code {result.returncode}",
        }
    except FileNotFoundError:
        result_payload["error"] = "sshpass is not installed on backend host"
    except subprocess.TimeoutExpired:
        result_payload["error"] = f"v4l2 probe timed out for {device}"
    except Exception as exc:
        result_payload["error"] = str(exc)

    V4L2_CAPS_CACHE[device] = {
        "expires_at": now + V4L2_CAPS_TTL_S,
        "value": result_payload,
    }
    return dict(result_payload)


async def _camera_config_with_runtime_caps(cam_id: str, config: dict) -> dict[str, object]:
    enriched = dict(config)
    device = str(enriched.get("device") or "").strip()
    if not device.startswith("/dev/video"):
        enriched["supported_source_formats"] = ["auto", "raw"]
        enriched["v4l2_formats_output"] = ""
        return enriched

    caps = await _fetch_remote_v4l2_caps(device, config=enriched)
    available = caps.get("supported_source_formats") or ["auto", "raw"]
    selected = str(enriched.get("source_format", "auto")).strip().lower() or "auto"
    if selected not in available:
        selected = "auto"
    enriched["source_format"] = selected
    enriched["supported_source_formats"] = available
    enriched["v4l2_formats_output"] = caps.get("v4l2_formats_output", "")
    enriched["v4l2_caps_error"] = caps.get("error")
    return enriched


async def _configs_with_runtime_caps(configs: dict[str, dict]) -> dict[str, dict]:
    enriched: dict[str, dict] = {}
    for cam_id, config in configs.items():
        enriched[cam_id] = await _camera_config_with_runtime_caps(cam_id, config)
    return enriched


class CameraMetrics(BaseModel):
    """Real-time camera metrics."""
    bandwidth_mbps: float
    latency_ms: float
    actual_fps: float
    frame_count: int
    last_update: str


# Hardcoded robot cameras
ROBOT_CAMERAS = [
    {"id": "http:robot_cam1", "name": "Robot Camera 1", "url": "http://192.168.2.50:8081/?action=stream", "port": 8081, "device": "/dev/video0"},
    {"id": "http:robot_cam2", "name": "Robot Camera 2", "url": "http://192.168.2.50:8082/?action=stream", "port": 8082, "device": "/dev/video2"},
    {"id": "http:robot_cam3", "name": "Robot Camera 3", "url": "http://192.168.2.50:8083/?action=stream", "port": 8083, "device": "/dev/video4"},
    {"id": "http:robot_cam4", "name": "Robot Camera 4", "url": "http://192.168.2.50:8084/?action=stream", "port": 8084, "device": "/dev/video6"},
]


# Standalone-vision compatible camera configs used by /vision/api/* routes.
STANDALONE_CAMERA_CONFIGS: dict[str, dict] = load_standalone_camera_configs()


def _reload_standalone_camera_configs() -> dict[str, dict]:
    STANDALONE_CAMERA_CONFIGS.clear()
    STANDALONE_CAMERA_CONFIGS.update(load_standalone_camera_configs())
    return STANDALONE_CAMERA_CONFIGS


def _persist_standalone_camera_configs() -> dict[str, dict]:
    normalized_configs = save_standalone_camera_configs(STANDALONE_CAMERA_CONFIGS)
    STANDALONE_CAMERA_CONFIGS.clear()
    STANDALONE_CAMERA_CONFIGS.update(normalized_configs)
    return STANDALONE_CAMERA_CONFIGS


async def _refresh_standalone_camera_configs() -> dict[str, dict]:
    # Only reload from disk when nothing is loaded yet (startup / explicit rescan).
    # Reloading on every 5-second poll overwrites the consolidated in-memory
    # state with the stale per-node cameras.json content.
    if not STANDALONE_CAMERA_CONFIGS:
        _reload_standalone_camera_configs()
    for config in STANDALONE_CAMERA_CONFIGS.values():
        normalize_standalone_camera_config(config)

    discovered = await _discover_remote_v4l2_cameras([], include_known_devices=True)
    camera_groups = AUTO_DISCOVERY_CACHE.get("camera_groups") or []

    if camera_groups:
        # One card per physical camera, collapsing any previously per-node expansion.
        _consolidate_configs_by_groups(STANDALONE_CAMERA_CONFIGS, camera_groups)
        _ensure_unique_target_ports(STANDALONE_CAMERA_CONFIGS)
        # Persist immediately so cameras.json stays correct across restarts.
        save_standalone_camera_configs(STANDALONE_CAMERA_CONFIGS)
    elif discovered:
        # Groups not available yet; fall back to per-node (first node only per new device).
        existing_devices = {
            str(cfg.get("device"))
            for cfg in STANDALONE_CAMERA_CONFIGS.values()
            if isinstance(cfg, dict)
        }
        for index, cam in enumerate(
            [c for c in discovered if c.get("device") not in existing_devices],
            start=len(STANDALONE_CAMERA_CONFIGS) + 1,
        ):
            cam_id = str(index)
            template = next(iter(STANDALONE_CAMERA_CONFIGS.values()), {})
            new_cfg = dict(template) if isinstance(template, dict) else {}
            new_cfg["device"] = cam["device"]
            new_cfg["target_port"] = 2139 + index
            new_cfg["sender_running"] = False
            new_cfg["receiver_running"] = False
            normalize_standalone_camera_config(new_cfg)
            STANDALONE_CAMERA_CONFIGS[cam_id] = new_cfg

    if _ensure_unique_target_ports(STANDALONE_CAMERA_CONFIGS):
        save_standalone_camera_configs(STANDALONE_CAMERA_CONFIGS)

    return STANDALONE_CAMERA_CONFIGS


@router.get("/api/cameras")
async def get_standalone_cameras(
    force: bool = Query(False, description="Force fresh sender/listener status check"),
) -> dict[str, dict]:
    """Return per-camera configs and process status for standalone-compatible UI."""
    try:
        await _refresh_standalone_camera_configs()

        await asyncio.to_thread(standalone_camera_controller.sync_statuses, STANDALONE_CAMERA_CONFIGS, force=force)
        return await _configs_with_runtime_caps(STANDALONE_CAMERA_CONFIGS)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read camera statuses: {exc}") from exc


@router.get("/api/camera-options")
async def get_standalone_camera_options() -> dict[str, object]:
    """Expose static dropdown options required by the standalone-style frontend."""
    return {
        "execution_modes": list(EXECUTION_MODES),
        "source_format_modes": list(SOURCE_FORMAT_MODES),
        "zoom_options": list(ZOOM_FACTORS.keys()),
        "resolution_presets": RESOLUTION_PRESETS,
    }


@router.put("/api/cameras/{cam_id}")
async def update_standalone_camera(cam_id: str, payload: StandaloneCameraUpdate) -> dict[str, object]:
    await _refresh_standalone_camera_configs()
    if cam_id not in STANDALONE_CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        updates = payload.model_dump(exclude_unset=True)
        await asyncio.to_thread(standalone_camera_controller.sync_statuses, STANDALONE_CAMERA_CONFIGS, force=True)
        sender_was_running = bool(STANDALONE_CAMERA_CONFIGS[cam_id].get("sender_running", False))

        STANDALONE_CAMERA_CONFIGS[cam_id].update(updates)
        normalize_standalone_camera_config(STANDALONE_CAMERA_CONFIGS[cam_id])
        if _ensure_unique_target_ports(STANDALONE_CAMERA_CONFIGS):
            _persist_standalone_camera_configs()

        # Apply should recreate active sender with the updated settings.
        if sender_was_running:
            await asyncio.to_thread(standalone_camera_controller.stop_sender, cam_id, STANDALONE_CAMERA_CONFIGS[cam_id])
            await asyncio.to_thread(standalone_camera_controller.start_sender, cam_id, STANDALONE_CAMERA_CONFIGS[cam_id])

        await asyncio.to_thread(standalone_camera_controller.sync_statuses, STANDALONE_CAMERA_CONFIGS, force=True)
        _persist_standalone_camera_configs()
        return await _camera_config_with_runtime_caps(cam_id, STANDALONE_CAMERA_CONFIGS[cam_id])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to apply camera {cam_id} settings: {exc}") from exc


@router.post("/api/cameras/{cam_id}/sender/start")
async def start_standalone_sender(cam_id: str) -> dict[str, str]:
    await _refresh_standalone_camera_configs()
    if cam_id not in STANDALONE_CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        normalize_standalone_camera_config(STANDALONE_CAMERA_CONFIGS[cam_id])
        if _ensure_unique_target_ports(STANDALONE_CAMERA_CONFIGS):
            _persist_standalone_camera_configs()
        await asyncio.to_thread(standalone_camera_controller.start_sender, cam_id, STANDALONE_CAMERA_CONFIGS[cam_id])
        await asyncio.to_thread(standalone_camera_controller.sync_statuses, STANDALONE_CAMERA_CONFIGS, force=True)
        _persist_standalone_camera_configs()
        return {"status": "sender started"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start sender for camera {cam_id}: {exc}") from exc


@router.post("/api/cameras/{cam_id}/sender/stop")
async def stop_standalone_sender(cam_id: str) -> dict[str, str]:
    await _refresh_standalone_camera_configs()
    if cam_id not in STANDALONE_CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        await asyncio.to_thread(standalone_camera_controller.stop_sender, cam_id, STANDALONE_CAMERA_CONFIGS[cam_id])
        await asyncio.to_thread(standalone_camera_controller.sync_statuses, STANDALONE_CAMERA_CONFIGS, force=True)
        _persist_standalone_camera_configs()
        return {"status": "sender stopped"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to stop sender for camera {cam_id}: {exc}") from exc


@router.post("/api/cameras/{cam_id}/receiver/start")
async def start_standalone_receiver(cam_id: str) -> dict[str, str]:
    await _refresh_standalone_camera_configs()
    if cam_id not in STANDALONE_CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        normalize_standalone_camera_config(STANDALONE_CAMERA_CONFIGS[cam_id])
        if _ensure_unique_target_ports(STANDALONE_CAMERA_CONFIGS):
            _persist_standalone_camera_configs()
        await asyncio.to_thread(standalone_camera_controller.start_receiver, cam_id, STANDALONE_CAMERA_CONFIGS[cam_id])
        await asyncio.to_thread(standalone_camera_controller.sync_statuses, STANDALONE_CAMERA_CONFIGS, force=True)
        _persist_standalone_camera_configs()
        return {"status": "receiver started"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start receiver for camera {cam_id}: {exc}") from exc


@router.post("/api/cameras/{cam_id}/receiver/stop")
async def stop_standalone_receiver(cam_id: str) -> dict[str, str]:
    await _refresh_standalone_camera_configs()
    if cam_id not in STANDALONE_CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")

    try:
        standalone_camera_controller.stop_receiver(cam_id, STANDALONE_CAMERA_CONFIGS[cam_id])
        standalone_camera_controller.sync_statuses(STANDALONE_CAMERA_CONFIGS, force=True)
        _persist_standalone_camera_configs()
        return {"status": "receiver stopped"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to stop receiver for camera {cam_id}: {exc}") from exc

@router.get("/cameras")
async def list_cameras(discover: bool = Query(False, description="Run SSH auto-discovery for V4L2 cameras")) -> dict[str, object]:
    """
    List all available cameras.
    Returning both GStreamer and HTTP MJPEG cameras.
    """
    cameras = []
    
    try:
        import sys
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        
        from config.camera_config import CAMERAS
        
        for cam_config in CAMERAS:
            if cam_config.get('enabled', True):
                if cam_config.get('type') == 'gstreamer':
                    cameras.append({
                        "id": f"gstreamer:{cam_config['id']}",
                        "name": cam_config['name'],
                        "url": cam_config.get('url'),
                        "device": cam_config.get('device'),
                        "udp_port": cam_config.get('udp_port'),
                        "available": True,
                        "type": "gstreamer",
                        "source": "camera_config"
                    })
                elif cam_config.get('type') == 'http_mjpeg':
                    cameras.append({
                        "id": f"http:{cam_config['id']}",
                        "name": cam_config['name'],
                        "url": cam_config.get('url'),
                        "available": True,
                        "type": "http_mjpeg",
                        "source": "camera_config"
                    })
        logger.info(f"Loaded cameras from camera_config.py")
    except Exception as e:
        logger.warning(f"Error loading camera_config.py: {e}")

    # Load custom cameras from config
    try:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "remote_cameras.json")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                for cam in config.get('cameras', []):
                    if cam.get('enabled', True):
                        cam_id = cam['id']
                        if not any(c['id'] == cam_id for c in cameras):
                            cam_obj = {
                                "id": cam['id'],
                                "name": cam['name'],
                                "available": True,
                                "type": cam.get('type', 'http_mjpeg'),
                                "source": "config_file"
                            }
                            if cam_obj['type'] == 'gstreamer':
                                cam_obj['udp_port'] = cam.get('udp_port')
                            else:
                                cam_obj['url'] = cam.get('url')
                            cameras.append(cam_obj)
                logger.info(f"Loaded custom cameras from config file")
    except Exception as e:
        logger.info(f"No custom camera config found: {e}")

    # Auto-discovery is opt-in (button/manual action), not automatic on every request.
    if discover:
        discovered_cameras = await _discover_remote_v4l2_cameras(cameras, include_known_devices=True)
        camera_groups = AUTO_DISCOVERY_CACHE.get("camera_groups") or []
        if discovered_cameras:
            return {"cameras": discovered_cameras, "camera_groups": camera_groups}
        diagnostics = _autodiscovery_diagnostics()
        return {
            "cameras": [],
            "camera_groups": [],
            "message": (
                f"Autodiscovery found 0 devices on {diagnostics.get('last_probe_host')}."
                f" {diagnostics.get('last_error') or ''}"
            ).strip(),
            "diagnostics": diagnostics,
        }

    # Return results
    return {"cameras": cameras}


@router.post("/cameras/discover")
async def discover_cameras() -> dict[str, object]:
    """Run one-shot SSH V4L2 auto-discovery and return the merged camera list."""
    return await list_cameras(discover=True)


@router.get("/cameras/discovery-debug")
async def camera_discovery_debug(force: bool = Query(True, description="Force a new remote probe")) -> dict[str, object]:
    """Return raw SSH probe output from `v4l2-ctl --list-devices` for diagnostics."""
    if force:
        AUTO_DISCOVERY_CACHE["expires_at"] = 0.0

    probe_result = await _run_remote_v4l2_probe([])
    AUTO_DISCOVERY_CACHE["last_probe_host"] = probe_result.get("ssh_host")
    AUTO_DISCOVERY_CACHE["last_probe"] = probe_result

    output = f"{probe_result.get('stdout', '')}\n{probe_result.get('stderr', '')}"
    devices = sorted(set(re.findall(r"/dev/video\d+", output)))
    if probe_result.get("error"):
        AUTO_DISCOVERY_CACHE["last_error"] = str(probe_result.get("error"))
    elif not devices:
        AUTO_DISCOVERY_CACHE["last_error"] = "No /dev/video* devices detected by remote v4l2-ctl"
    else:
        AUTO_DISCOVERY_CACHE["last_error"] = None

    return {
        "devices": devices,
        "diagnostics": _autodiscovery_diagnostics(),
        "probe": {
            "ssh_host": probe_result.get("ssh_host"),
            "ssh_user": probe_result.get("ssh_user"),
            "ssh_port": probe_result.get("ssh_port"),
            "remote_command": probe_result.get("remote_command"),
            "exit_code": probe_result.get("exit_code"),
            "timed_out": probe_result.get("timed_out"),
            "error": probe_result.get("error"),
            "stdout": probe_result.get("stdout"),
            "stderr": probe_result.get("stderr"),
        },
    }


@router.get("/metrics/{camera_id:path}")
async def get_camera_metrics(camera_id: str = Path(..., description="Camera ID")) -> CameraMetrics:
    """
    Get real-time metrics for a specific camera.
    Returns bandwidth, latency, FPS, etc.
    """
    try:
        if camera_id not in camera_metrics:
            # Return default metrics if not streaming
            return CameraMetrics(
                bandwidth_mbps=0.0,
                latency_ms=0.0,
                actual_fps=0.0,
                frame_count=0,
                last_update=datetime.now().isoformat()
            )
        
        metrics = camera_metrics[camera_id]
        return CameraMetrics(**metrics)
    except Exception as e:
        logger.error(f"Error getting camera metrics for {camera_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Screen session prefix used on the robot for camera streams
CAMERA_SCREEN_PREFIX = "cam"


def _camera_screen_name(port: int) -> str:
    """Derive the screen session name from the camera port (matches shell script)."""
    port_to_index = {8081: 1, 8082: 2, 8083: 3, 8084: 4}
    idx = port_to_index.get(port, port)
    return f"{CAMERA_SCREEN_PREFIX}{idx}"


async def restart_remote_stream(port: int, device: str, resolution: str, fps: int):
    """
    SSH into robot and restart mjpg_streamer inside a screen session.
    Uses -y (YUYV) -q 50 (JPEG quality) flags.
    """
    host = "192.168.2.50"
    user = "lrt_geeokom"
    password = "qwerty"
    session = _camera_screen_name(port)

    # 1. Kill existing screen session and free the port
    kill_cmd = (
        f"screen -S {session} -X quit 2>/dev/null; "
        f"fuser -k -n tcp {port} 2>/dev/null; "
        f"pkill -f \"gst-launch-1.0.*{device}\" 2>/dev/null || true; "
        f"pkill -f \"mjpg_streamer.*{device}\" 2>/dev/null || true; "
        f"sleep 1"
    )

    # 2. Start new mjpg_streamer inside a detached screen
    streamer_cmd = (
        f"mjpg_streamer "
        f"-i \\\"input_uvc.so -d {device} -r {resolution} -f {fps} -y -q 50\\\" "
        f"-o \\\"output_http.so -p {port}\\\""
    )
    start_cmd = f"screen -dmS {session} bash -lc '{streamer_cmd}'"

    full_cmd = f"{kill_cmd} && {start_cmd}"

    ssh_cmd = [
        "sshpass", "-p", password,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
        f"{user}@{host}",
        full_cmd
    ]

    logger.info(f"Restarting remote stream on port {port}: {resolution} @ {fps} FPS (screen={session})")
    try:
        await asyncio.to_thread(subprocess.run, ssh_cmd, timeout=15, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to restart stream via SSH: {e}")
        return False
    except Exception as e:
        logger.error(f"Error executing SSH command: {e}")
        return False


@router.post("/set_params/{camera_id:path}")
async def set_camera_params(
    camera_id: str = Path(..., description="Camera ID"),
    settings: CameraSettings = None
) -> dict[str, object]:
    """
    Update camera parameters (resolution, FPS, compression, etc.).
    """
    try:
        # Check if it's one of our robot cameras
        robot_cam = next((c for c in ROBOT_CAMERAS if c["id"] == camera_id), None)
        
        if robot_cam:
            # Check if restart is actually needed
            # We assume default state (640x480, 15fps) if not known
            current_settings = active_streams.get(camera_id, {}).get("settings")
            
            should_restart = True
            
            # If we know the current settings, check if they match
            if current_settings:
                if (current_settings.get("resolution") == settings.resolution and 
                    current_settings.get("fps") == settings.fps):
                    should_restart = False
            else:
                 # If unknown, check if request matches the known boot default (640x480, 15fps)
                 # This prevents restart on first "Apply" if settings are default
                 if settings.resolution == "640x480" and settings.fps == 15:
                     should_restart = False
            
            if should_restart:
                # It's a remote robot camera - restart stream via SSH
                success = await restart_remote_stream(
                    port=robot_cam["port"],
                    device=robot_cam["device"],
                    resolution=settings.resolution,
                    fps=settings.fps
                )
                if not success:
                     raise HTTPException(status_code=500, detail="Failed to restart remote stream")
                message = f"Remote camera {camera_id} restarted with {settings.resolution} @ {settings.fps} FPS"
            else:
                message = f"Remote camera {camera_id} settings updated (Stream restart skipped)"
            
        else:
            from services.ros_node import get_ros_node
            ros_node = get_ros_node()
            if ros_node:
                # ROS2 param update logic (for USB cams connected to Jetson explicitly handled via ROS)
                pass 
            message = f"Camera {camera_id} parameters updated (local/mock)"

        # Store settings for this camera
        if camera_id not in active_streams:
            active_streams[camera_id] = {}
        active_streams[camera_id]["settings"] = settings.dict()
        
        logger.info(message)
        
        return {
            "status": "success",
            "message": message,
            "settings": settings.dict(),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error setting camera parameters for {camera_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


from typing import Optional

class AddCameraRequest(BaseModel):
    """Request model for adding a new camera."""
    name: str
    type: str = "gstreamer"
    udp_port: Optional[int] = None
    url: Optional[str] = None


@router.post("/cameras/add")
async def add_camera(request: AddCameraRequest) -> dict[str, object]:
    """Add a new camera to the system (GStreamer or HTTP)."""
    try:
        import os
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "remote_cameras.json")
        
        # Create config directory if needed
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # Load existing config
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            config = {"cameras": []}
        
        cam_type = request.type
        
        # Determine camera config object based on type
        if cam_type == "gstreamer":
            if not request.udp_port:
                raise HTTPException(status_code=400, detail="udp_port is required for GStreamer cameras")
            camera_id = f"gstreamer:{request.name.lower().replace(' ', '_')}"
            new_camera = {
                "id": camera_id,
                "name": request.name,
                "udp_port": request.udp_port,
                "type": cam_type,
                "enabled": True
            }
            log_detail = f"Port: {request.udp_port}"
        else:
            cam_type = "http_mjpeg"
            if not request.url:
                raise HTTPException(status_code=400, detail="url is required for HTTP cameras")
            camera_id = f"http:{request.name.lower().replace(' ', '_')}"
            new_camera = {
                "id": camera_id,
                "name": request.name,
                "url": request.url,
                "type": cam_type,
                "enabled": True
            }
            log_detail = request.url
        
        # Check if already exists
        existing_ids = [cam.get('id') for cam in config['cameras']]
        if camera_id in existing_ids:
            raise HTTPException(status_code=400, detail=f"Camera with name '{request.name}' already exists")
        
        # Add new camera
        config['cameras'].append(new_camera)
        
        # Save config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Added camera: {camera_id} ({log_detail})")
        
        return {
            "status": "success",
            "message": "Camera added successfully",
            "camera": new_camera
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/cameras/{camera_id:path}")
async def remove_camera(camera_id: str = Path(..., description="Camera ID")) -> dict[str, object]:
    """Remove a camera from the system."""
    try:
        import os
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "remote_cameras.json")
        
        if not os.path.exists(config_path):
            raise HTTPException(status_code=404, detail="No cameras configured")
        
        # Load config
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Find and remove camera
        original_count = len(config['cameras'])
        config['cameras'] = [cam for cam in config['cameras'] if cam.get('id') != camera_id]
        
        if len(config['cameras']) == original_count:
            raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
        
        # Save config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Removed camera: {camera_id}")
        
        return {
            "status": "success",
            "message": f"Camera {camera_id} removed successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/cameras/{camera_id:path}")
async def update_camera(
    camera_id: str = Path(..., description="Camera ID"),
    request: AddCameraRequest = None
) -> dict[str, object]:
    """Update camera details."""
    try:
        import os
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "remote_cameras.json")
        
        if not os.path.exists(config_path):
            raise HTTPException(status_code=404, detail="No cameras configured")
        
        # Load config
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Find and update camera
        found = False
        for cam in config['cameras']:
            if cam.get('id') == camera_id:
                cam['name'] = request.name
                cam['url'] = request.url
                found = True
                break
        
        if not found:
            raise HTTPException(status_code=404, detail=f"Camera {camera_id} not found")
        
        # Save config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        logger.info(f"Updated camera: {camera_id}")
        
        return {
            "status": "success",
            "message": f"Camera {camera_id} updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/stream/{camera_id:path}")
async def camera_stream_websocket(websocket: WebSocket, camera_id: str):
    """
    WebSocket endpoint for streaming camera images.
    Subscribes to ROS2 image topic and sends base64-encoded JPEG frames.
    """
    await websocket.accept()
    logger.info(f"WebSocket connected for camera {camera_id}")
    
    # Initialize metrics
    if camera_id not in camera_metrics:
        camera_metrics[camera_id] = {
            "bandwidth_mbps": 0.0,
            "latency_ms": 0.0,
            "actual_fps": 0.0,
            "frame_count": 0,
            "last_update": datetime.now().isoformat(),
            "start_time": time.time(),
            "total_bytes": 0,
            "last_frame_time": time.time()
        }
    
    try:
        from services.ros_node import get_ros_node
        import rclpy
        from sensor_msgs.msg import Image, CompressedImage
        from cv_bridge import CvBridge
        import cv2
        import numpy as np
        
        ros_node = get_ros_node()
        
        # Get camera settings
        settings = active_streams.get(camera_id, {}).get("settings", {})
        use_compressed = settings.get("compression", "compressed") == "compressed"
        jpeg_quality = settings.get("jpeg_quality", 50)
        
        # Get zoom parameters from preset
        zoom_preset = settings.get("zoom_preset", "none")
        zoom_x, zoom_y, zoom_width, zoom_height = get_zoom_params(zoom_preset)
        
        # Mock mode if ROS not available
        if not ros_node:
            logger.warning(f"ROS node not available, using mock stream for {camera_id}")
            frame_count = 0
            while True:
                try:
                    # Generate mock image
                    img = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
                    
                    # Add timestamp text
                    cv2.putText(img, f"Mock Camera {camera_id}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                    cv2.putText(img, f"Frame: {frame_count}", (10, 70),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    cv2.putText(img, datetime.now().strftime("%H:%M:%S.%f")[:-3], (10, 110),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                    
                    # Encode to JPEG
                    _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                    jpg_base64 = base64.b64encode(buffer).decode('utf-8')
                    
                    # Update metrics
                    metrics = camera_metrics[camera_id]
                    metrics["frame_count"] += 1
                    metrics["total_bytes"] += len(buffer)
                    current_time = time.time()
                    elapsed = current_time - metrics["start_time"]
                    if elapsed > 0:
                        metrics["actual_fps"] = metrics["frame_count"] / elapsed
                        metrics["bandwidth_mbps"] = (metrics["total_bytes"] * 8) / (elapsed * 1_000_000)
                    metrics["latency_ms"] = (current_time - metrics["last_frame_time"]) * 1000
                    metrics["last_frame_time"] = current_time
                    metrics["last_update"] = datetime.now().isoformat()
                    
                    # Send frame
                    await websocket.send_json({
                        "type": "frame",
                        "camera_id": camera_id,
                        "image": jpg_base64,
                        "timestamp": datetime.now().isoformat(),
                        "frame_number": frame_count,
                        "metrics": {
                            "bandwidth_mbps": round(metrics["bandwidth_mbps"], 2),
                            "latency_ms": round(metrics["latency_ms"], 2),
                            "actual_fps": round(metrics["actual_fps"], 1)
                        }
                    })
                    
                    frame_count += 1
                    await asyncio.sleep(1.0 / 10.0)  # 10 FPS for mock
                    
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected for camera {camera_id}")
                    break
                except Exception as e:
                    logger.error(f"Error in mock stream: {e}")
                    await asyncio.sleep(0.1)
        # HTTP/MJPEG camera (format: http:camera_name)
        elif camera_id.startswith("http:"):
            try:
                import aiohttp
                import io
                from PIL import Image as PILImage
                
                # Load camera config to get URL
                import os
                import json
                config_path = os.path.join(os.path.dirname(__file__), "..", "config", "remote_cameras.json")
                camera_url = None
                
                # CHECK HARDCODED ROBOT CAMERAS FIRST
                robot_cam = next((c for c in ROBOT_CAMERAS if c["id"] == camera_id), None)
                if robot_cam:
                    camera_url = robot_cam.get("url")
                
                # Check config file if not found
                if not camera_url and os.path.exists(config_path):
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        for cam in config.get('cameras', []):
                            if cam.get('id') == camera_id:
                                camera_url = cam.get('url')
                                break
                
                if not camera_url:
                    raise ValueError(f"Camera URL not found for {camera_id}")
                
                logger.info(f"Streaming HTTP camera from: {camera_url}")
                
                frame_count = 0
                async with aiohttp.ClientSession() as session:
                    async with session.get(camera_url) as response:
                        if response.status != 200:
                            raise ValueError(f"HTTP {response.status} from {camera_url}")
                        
                        # Read MJPEG stream
                        boundary = None
                        buffer = b''
                        
                        async for chunk in response.content.iter_any():
                            buffer += chunk
                            
                            # Find JPEG boundaries
                            if b'\xff\xd8' in buffer and b'\xff\xd9' in buffer:
                                start = buffer.find(b'\xff\xd8')
                                end = buffer.find(b'\xff\xd9', start) + 2
                                
                                if start != -1 and end > start:
                                    # Extract JPEG frame
                                    jpeg_data = buffer[start:end]
                                    buffer = buffer[end:]
                                    
                                    # Apply zoom if needed
                                    if zoom_width < 1.0 or zoom_height < 1.0:
                                        img = PILImage.open(io.BytesIO(jpeg_data))
                                        w, h = img.size
                                        x1 = int(w * zoom_x)
                                        y1 = int(h * zoom_y)
                                        x2 = int(w * (zoom_x + zoom_width))
                                        y2 = int(h * (zoom_y + zoom_height))
                                        img = img.crop((x1, y1, x2, y2))
                                        
                                        # Re-encode with quality setting
                                        output = io.BytesIO()
                                        img.save(output, format='JPEG', quality=jpeg_quality)
                                        jpeg_data = output.getvalue()
                                    
                                    jpg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
                                    
                                    # Update metrics
                                    metrics = camera_metrics[camera_id]
                                    metrics["frame_count"] += 1
                                    metrics["total_bytes"] += len(jpeg_data)
                                    current_time = time.time()
                                    elapsed = current_time - metrics["start_time"]
                                    if elapsed > 0:
                                        metrics["actual_fps"] = metrics["frame_count"] / elapsed
                                        metrics["bandwidth_mbps"] = (metrics["total_bytes"] * 8) / (elapsed * 1_000_000)
                                    metrics["latency_ms"] = (current_time - metrics["last_frame_time"]) * 1000
                                    metrics["last_frame_time"] = current_time
                                    metrics["last_update"] = datetime.now().isoformat()
                                    
                                    # Send frame
                                    await websocket.send_json({
                                        "type": "frame",
                                        "camera_id": camera_id,
                                        "image": jpg_base64,
                                        "timestamp": datetime.now().isoformat(),
                                        "frame_number": frame_count,
                                        "metrics": {
                                            "bandwidth_mbps": round(metrics["bandwidth_mbps"], 2),
                                            "latency_ms": round(metrics["latency_ms"], 2),
                                            "actual_fps": round(metrics["actual_fps"], 1)
                                        }
                                    })
                                    
                                    frame_count += 1
                                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected for HTTP camera {camera_id}")
            except aiohttp.client_exceptions.ClientConnectorError as e:
                logger.warning(f"HTTP camera {camera_id} is offline ({e})")
                try:
                    await websocket.send_json({"type": "error", "message": "Camera is offline or starting up"})
                    await asyncio.sleep(2.0)
                except:
                    pass
            except Exception as e:
                logger.error(f"HTTP camera stream error for {camera_id}: {e}")
                try:
                    await websocket.send_json({"type": "error", "message": "Stream error"})
                    await asyncio.sleep(1.0)
                except:
                    pass
        # GStreamer udp camera (format: gstreamer:camera_id)
        elif camera_id.startswith("gstreamer:"):
            pipeline = None
            try:
                import gi
                gi.require_version('Gst', '1.0')
                from gi.repository import Gst
                
                if not Gst.is_initialized():
                    Gst.init(None)

                # Find the udp port from CAMERAS config
                import os
                import sys
                backend_dir = os.path.dirname(os.path.dirname(__file__))
                if backend_dir not in sys.path:
                    sys.path.insert(0, backend_dir)
                from config.camera_config import CAMERAS
                
                matched_cam = next((c for c in CAMERAS if c["id"] == camera_id.split(':', 1)[1]), None)
                if not matched_cam or not matched_cam.get("udp_port"):
                    # Not in camera_config, try remote_cameras.json
                    try:
                        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "remote_cameras.json")
                        if os.path.exists(config_path):
                            with open(config_path, 'r') as f:
                                config = json.load(f)
                                for cam in config.get('cameras', []):
                                    if cam.get('id') == camera_id and cam.get('type') == 'gstreamer':
                                        matched_cam = cam
                                        break
                    except Exception as json_e:
                        logger.warning(f"Error checking remote_cameras for dynamic gstreamer config: {json_e}")

                if not matched_cam or not matched_cam.get("udp_port"):
                    raise ValueError(f"GStreamer camera config not found for {camera_id}")
                
                port = matched_cam["udp_port"]
                
                # Get camera settings
                settings = active_streams.get(camera_id, {}).get("settings", {})
                width = None
                height = None
                if settings.get("resolution"):
                    try:
                        width, height = map(int, settings.get("resolution").split("x"))
                    except Exception:
                        width = None
                        height = None
                fps = settings.get("fps", 30)
                jpeg_quality = settings.get("jpeg_quality", 50)
                zoom_preset = settings.get("zoom_preset", "none")

                # GStreamer pipeline to receive UDP h264 stream and encode to JPEG directly
                # Adding videoscale if width and height are provided
                scale_caps = f" ! videoscale ! video/x-raw,width={width},height={height}" if width and height else ""
                
                pipeline_string = (
                    f"udpsrc port={port} ! application/x-rtp,media=video,encoding-name=H264,payload=96 ! "
                    f"rtph264depay ! avdec_h264 ! videoconvert{scale_caps} ! "
                    f"jpegenc quality={jpeg_quality} ! appsink name=mysink drop=true max-buffers=1 emit-signals=true sync=false"
                )
                pipeline = Gst.parse_launch(pipeline_string)
                pipeline.set_state(Gst.State.PLAYING)
                sink = pipeline.get_by_name("mysink")
                if not sink:
                    raise RuntimeError(f"Unable to find appsink in GStreamer pipeline on port {port}")

                frame_count = 0
                loop = asyncio.get_event_loop()
                while True:
                    try:
                        # try-pull-sample with timeout 50ms to not block asyncio
                        sample = await loop.run_in_executor(None, sink.emit, "try-pull-sample", 50000000)
                        if not sample:
                            await asyncio.sleep(0.01)
                            continue

                        buf = sample.get_buffer()
                        ret, map_info = buf.map(Gst.MapFlags.READ)
                        if not ret:
                            continue
                            
                        # Get JPEG bytes directly from GStreamer buffer
                        jpeg_data = map_info.data
                        jpg_base64 = base64.b64encode(jpeg_data).decode('utf-8')
                        buf.unmap(map_info)

                        # Update metrics
                        if camera_id not in camera_metrics:
                            camera_metrics[camera_id] = {
                                "bandwidth_mbps": 0.0,
                                "latency_ms": 0.0,
                                "actual_fps": 0.0,
                                "frame_count": 0,
                                "last_update": datetime.now().isoformat(),
                                "start_time": time.time(),
                                "total_bytes": 0,
                                "last_frame_time": time.time()
                            }
                        metrics = camera_metrics[camera_id]
                        metrics["frame_count"] += 1
                        metrics["total_bytes"] += len(jpeg_data)
                        current_time = time.time()
                        elapsed = current_time - metrics["start_time"]
                        if elapsed > 0:
                            metrics["actual_fps"] = metrics["frame_count"] / elapsed
                            metrics["bandwidth_mbps"] = (metrics["total_bytes"] * 8) / (elapsed * 1_000_000)
                        metrics["latency_ms"] = (current_time - metrics["last_frame_time"]) * 1000
                        metrics["last_frame_time"] = current_time
                        metrics["last_update"] = datetime.now().isoformat()

                        # Send frame
                        await websocket.send_json({
                            "type": "frame",
                            "camera_id": camera_id,
                            "image": jpg_base64,
                            "timestamp": datetime.now().isoformat(),
                            "frame_number": frame_count,
                            "metrics": {
                                "bandwidth_mbps": round(metrics["bandwidth_mbps"], 2),
                                "latency_ms": round(metrics["latency_ms"], 2),
                                "actual_fps": round(metrics["actual_fps"], 1)
                            }
                        })

                        frame_count += 1
                        # Sleep to respect fps 
                        await asyncio.sleep(1.0 / max(1, fps))

                    except WebSocketDisconnect:
                        logger.info(f"WebSocket disconnected for gstreamer {camera_id}")
                        break
                    except Exception as e:
                        logger.error(f"Error streaming from gstreamer {camera_id}: {e}")
                        await asyncio.sleep(0.1)

                # Cleanup
                try:
                    pipeline.set_state(Gst.State.NULL)
                except Exception:
                    pass
            except Exception as e:
                logger.error(f"GStreamer stream error for {camera_id}: {e}")
                await websocket.send_json({"type": "error", "message": str(e)})

        # V4L2 camera (format: v4l:/dev/video10)
        elif camera_id.startswith("v4l:"):
            try:
                import cv2
                import numpy as np

                device_path = camera_id.split(':', 1)[1]

                # Get camera settings
                settings = active_streams.get(camera_id, {}).get("settings", {})
                width = None
                height = None
                if settings.get("resolution"):
                    try:
                        width, height = map(int, settings.get("resolution").split("x"))
                    except Exception:
                        width = None
                        height = None
                fps = settings.get("fps", 30)
                jpeg_quality = settings.get("jpeg_quality", 50)
                zoom_preset = settings.get("zoom_preset", "none")
                zoom_x, zoom_y, zoom_width, zoom_height = get_zoom_params(zoom_preset)

                cap = cv2.VideoCapture(device_path, cv2.CAP_V4L2)
                if cap is None or not cap.isOpened():
                    raise RuntimeError(f"Unable to open device {device_path}")

                # Apply resolution/fps if provided
                if width and height:
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                if fps:
                    cap.set(cv2.CAP_PROP_FPS, fps)

                frame_count = 0
                while True:
                    try:
                        ret, frame = cap.read()
                        if not ret:
                            await asyncio.sleep(0.05)
                            continue

                        # Apply zoom/ROI if configured
                        if zoom_width < 1.0 or zoom_height < 1.0:
                            h, w = frame.shape[:2]
                            x1 = int(w * zoom_x)
                            y1 = int(h * zoom_y)
                            x2 = int(w * (zoom_x + zoom_width))
                            y2 = int(h * (zoom_y + zoom_height))
                            frame = frame[y1:y2, x1:x2]

                        # Encode to JPEG
                        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                        jpg_base64 = base64.b64encode(buffer).decode('utf-8')

                        # Update metrics
                        if camera_id not in camera_metrics:
                            camera_metrics[camera_id] = {
                                "bandwidth_mbps": 0.0,
                                "latency_ms": 0.0,
                                "actual_fps": 0.0,
                                "frame_count": 0,
                                "last_update": datetime.now().isoformat(),
                                "start_time": time.time(),
                                "total_bytes": 0,
                                "last_frame_time": time.time()
                            }
                        metrics = camera_metrics[camera_id]
                        metrics["frame_count"] += 1
                        metrics["total_bytes"] += len(buffer)
                        current_time = time.time()
                        elapsed = current_time - metrics["start_time"]
                        if elapsed > 0:
                            metrics["actual_fps"] = metrics["frame_count"] / elapsed
                            metrics["bandwidth_mbps"] = (metrics["total_bytes"] * 8) / (elapsed * 1_000_000)
                        metrics["latency_ms"] = (current_time - metrics["last_frame_time"]) * 1000
                        metrics["last_frame_time"] = current_time
                        metrics["last_update"] = datetime.now().isoformat()

                        # Send frame
                        await websocket.send_json({
                            "type": "frame",
                            "camera_id": camera_id,
                            "image": jpg_base64,
                            "timestamp": datetime.now().isoformat(),
                            "frame_number": frame_count,
                            "metrics": {
                                "bandwidth_mbps": round(metrics["bandwidth_mbps"], 2),
                                "latency_ms": round(metrics["latency_ms"], 2),
                                "actual_fps": round(metrics["actual_fps"], 1)
                            }
                        })

                        frame_count += 1
                        # Sleep to respect fps
                        await asyncio.sleep(1.0 / max(1, fps))

                    except WebSocketDisconnect:
                        logger.info(f"WebSocket disconnected for device {camera_id}")
                        break
                    except Exception as e:
                        logger.error(f"Error streaming from device {device_path}: {e}")
                        await asyncio.sleep(0.1)

                # Cleanup
                try:
                    cap.release()
                except Exception:
                    pass
            except Exception as e:
                logger.warning(f"Device {camera_id} is offline or unavailable ({e})")
                try:
                    await websocket.send_json({"type": "error", "message": "Camera device is unavailable"})
                    await asyncio.sleep(2.0)
                except:
                    pass
        
        # ROS2 camera streaming (default fallback)
        else:
            bridge = CvBridge()
            frame_count = 0
            last_image = None
            image_lock = asyncio.Lock()
            
            # Determine topic based on compression setting
            if use_compressed:
                topic_name = f"/{camera_id}/image_raw/compressed"
                
                def image_callback(msg: CompressedImage):
                    nonlocal last_image
                    asyncio.run(image_lock.acquire())
                    try:
                        last_image = msg
                    finally:
                        image_lock.release()
                
                subscription = ros_node.create_subscription(
                    CompressedImage,
                    topic_name,
                    image_callback,
                    10
                )
            else:
                topic_name = f"/{camera_id}/image_raw"
                
                def image_callback(msg: Image):
                    nonlocal last_image
                    asyncio.run(image_lock.acquire())
                    try:
                        last_image = msg
                    finally:
                        image_lock.release()
                
                subscription = ros_node.create_subscription(
                    Image,
                    topic_name,
                    image_callback,
                    10
                )
            
            logger.info(f"Subscribed to {topic_name}")
            
            # Stream loop
            while True:
                try:
                    await asyncio.sleep(0.033)  # ~30 FPS max
                    
                    async with image_lock:
                        if last_image is None:
                            continue
                        
                        current_image = last_image
                        last_image = None
                    
                    # Convert to OpenCV image
                    if use_compressed:
                        np_arr = np.frombuffer(current_image.data, np.uint8)
                        cv_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    else:
                        cv_image = bridge.imgmsg_to_cv2(current_image, desired_encoding='bgr8')
                    
                    # Apply zoom/ROI if configured
                    if zoom_width < 1.0 or zoom_height < 1.0:
                        h, w = cv_image.shape[:2]
                        x1 = int(w * zoom_x)
                        y1 = int(h * zoom_y)
                        x2 = int(w * (zoom_x + zoom_width))
                        y2 = int(h * (zoom_y + zoom_height))
                        cv_image = cv_image[y1:y2, x1:x2]
                    
                    # Encode to JPEG
                    _, buffer = cv2.imencode('.jpg', cv_image, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                    jpg_base64 = base64.b64encode(buffer).decode('utf-8')
                    
                    # Update metrics
                    metrics = camera_metrics[camera_id]
                    metrics["frame_count"] += 1
                    metrics["total_bytes"] += len(buffer)
                    current_time = time.time()
                    elapsed = current_time - metrics["start_time"]
                    if elapsed > 0:
                        metrics["actual_fps"] = metrics["frame_count"] / elapsed
                        metrics["bandwidth_mbps"] = (metrics["total_bytes"] * 8) / (elapsed * 1_000_000)
                    metrics["latency_ms"] = (current_time - metrics["last_frame_time"]) * 1000
                    metrics["last_frame_time"] = current_time
                    metrics["last_update"] = datetime.now().isoformat()
                    
                    # Send frame
                    await websocket.send_json({
                        "type": "frame",
                        "camera_id": camera_id,
                        "image": jpg_base64,
                        "timestamp": datetime.now().isoformat(),
                        "frame_number": frame_count,
                        "metrics": {
                            "bandwidth_mbps": round(metrics["bandwidth_mbps"], 2),
                            "latency_ms": round(metrics["latency_ms"], 2),
                            "actual_fps": round(metrics["actual_fps"], 1)
                        }
                    })
                    
                    frame_count += 1
                    
                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected for camera {camera_id}")
                    ros_node.destroy_subscription(subscription)
                    break
                except Exception as e:
                    logger.error(f"Error in ROS2 stream: {e}")
                    await asyncio.sleep(0.1)
    
    except Exception as e:
        logger.error(f"Fatal error in camera stream for {camera_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except:
            pass
    finally:
        # Clean up metrics
        if camera_id in camera_metrics:
            del camera_metrics[camera_id]
        logger.info(f"Camera stream ended for {camera_id}")


# Store active camera processes (for remote control)
camera_processes = {}


@router.get("/camera_config")
async def get_camera_config() -> dict[str, object]:
    """Get the camera configuration from camera_config.py (Desktop app style) and json config."""
    try:
        import sys
        import os
        import json
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        
        from config.camera_config import (
            CAMERAS, ROBOT_IP, CAM_RECEIVER_IP,
            CAMERA_1_HTTP_PORT, CAMERA_2_HTTP_PORT, 
            CAMERA_3_HTTP_PORT, CAMERA_4_HTTP_PORT,
            CAMERA_1_UDP_PORT, CAMERA_2_UDP_PORT,
            CAMERA_3_UDP_PORT, CAMERA_4_UDP_PORT,
            WEB_RESOLUTION, WEB_FRAMERATE
        )
        
        # Override receiver_ip from json if available
        receiver_ip = CAM_RECEIVER_IP
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "remote_cameras.json")
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
                if 'receiver_ip' in config:
                    receiver_ip = config['receiver_ip']
        
        return {
            "status": "success",
            "cameras": CAMERAS,
            "robot_ip": ROBOT_IP,
            "receiver_ip": receiver_ip,
            "web_settings": {
                "resolution": WEB_RESOLUTION,
                "framerate": WEB_FRAMERATE
            }
        }
    except ImportError:
        raise HTTPException(status_code=404, detail="camera_config.py not found. Please create it based on the desktop app configuration.")
    except Exception as e:
        logger.error(f"Error loading camera config: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ReceiverIpRequest(BaseModel):
    ip: str

@router.post("/camera_config/receiver_ip")
async def update_receiver_ip(request: ReceiverIpRequest) -> dict[str, object]:
    """Update the GStreamer receiver IP in the JSON configuration."""
    try:
        import os
        import json
        config_path = os.path.join(os.path.dirname(__file__), "..", "config", "remote_cameras.json")
        
        # Create directory if needed
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        
        # Load existing config
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = json.load(f)
        else:
            config = {"cameras": []}
            
        config['receiver_ip'] = request.ip
        
        # Save config
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
            
        logger.info(f"Updated receiver_ip to {request.ip}")
        return {
            "status": "success",
            "message": "Receiver IP updated perfectly",
            "receiver_ip": request.ip
        }
    except Exception as e:
        logger.error(f"Error updating receiver IP: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CameraStartRequest(BaseModel):
    """Request to start a camera stream on the robot."""
    camera_id: str
    robot_ip: Optional[str] = None  # Override robot IP if needed


@router.post("/start_camera")
async def start_camera_on_robot(request: CameraStartRequest) -> dict[str, object]:
    """
    Start a camera stream on the robot (similar to desktop app approach).
    Runs mjpg-streamer on the robot to make camera available via HTTP.
    """
    try:
        import sys
        import os
        import subprocess
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        
        from config.camera_config import CAMERAS, ROBOT_IP, get_mjpg_streamer_cmd
        
        robot_ip = request.robot_ip or ROBOT_IP
        
        # Find camera config
        camera_config = None
        for cam in CAMERAS:
            if cam['id'] == request.camera_id:
                camera_config = cam
                break
        
        if not camera_config:
            raise HTTPException(status_code=404, detail=f"Camera {request.camera_id} not found in configuration")
        
        # Generate command
        device = camera_config['device']
        port = camera_config['http_port']
        cmd = get_mjpg_streamer_cmd(device, port, camera_config['name'])
        
        # If running locally, start process directly
        if robot_ip in ['localhost', '127.0.0.1'] or robot_ip == os.popen('hostname -I').read().split()[0]:
            # Kill existing process if running
            if request.camera_id in camera_processes:
                try:
                    camera_processes[request.camera_id].terminate()
                    camera_processes[request.camera_id].wait(timeout=5)
                except:
                    pass
            
            # Also kill any existing mjpg_streamer on this port
            subprocess.run(f"pkill -f 'mjpg_streamer.*-p {port}'", shell=True, check=False)
            
            # Start new process
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setpgrp
            )
            camera_processes[request.camera_id] = process
            
            logger.info(f"Started camera {request.camera_id} on port {port} (PID: {process.pid})")
            
            return {
                "status": "success",
                "message": f"Camera {request.camera_id} started on port {port}",
                "camera_id": request.camera_id,
                "url": camera_config['url'],
                "port": port,
                "pid": process.pid
            }
        else:
            # Remote robot - provide SSH command
            ssh_cmd = f"ssh {robot_ip} '{cmd}'"
            return {
                "status": "info",
                "message": f"Camera {request.camera_id} requires remote execution",
                "camera_id": request.camera_id,
                "robot_ip": robot_ip,
                "command": cmd,
                "ssh_command": ssh_cmd,
                "help": "Run this command on the robot or use SSH to execute remotely"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop_camera/{camera_id}")
async def stop_camera_on_robot(camera_id: str) -> dict[str, object]:
    """Stop a camera stream on the robot."""
    try:
        # Stop local process if exists
        if camera_id in camera_processes:
            try:
                camera_processes[camera_id].terminate()
                camera_processes[camera_id].wait(timeout=5)
                del camera_processes[camera_id]
                logger.info(f"Stopped camera {camera_id}")
                return {
                    "status": "success",
                    "message": f"Camera {camera_id} stopped"
                }
            except Exception as e:
                logger.error(f"Error stopping camera process: {e}")
        
        # Try to kill by port
        import sys
        import os
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        
        from config.camera_config import CAMERAS
        
        for cam in CAMERAS:
            if cam['id'] == camera_id:
                port = cam['http_port']
                result = subprocess.run(
                    f"pkill -f 'mjpg_streamer.*-p {port}'",
                    shell=True,
                    capture_output=True
                )
                return {
                    "status": "success",
                    "message": f"Attempted to stop camera {camera_id} on port {port}"
                }
        
        return {
            "status": "warning",
            "message": f"Camera {camera_id} not found or not running"
        }
        
    except Exception as e:
        logger.error(f"Error stopping camera: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/camera_status")
async def get_camera_status() -> dict[str, object]:
    """Get status of all configured cameras."""
    try:
        import sys
        import os
        import subprocess
        backend_dir = os.path.dirname(os.path.dirname(__file__))
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        
        from config.camera_config import CAMERAS
        
        status_list = []
        for cam in CAMERAS:
            # Check if process is running
            port = cam['http_port']
            result = subprocess.run(
                f"pgrep -f 'mjpg_streamer.*-p {port}'",
                shell=True,
                capture_output=True
            )
            is_running = result.returncode == 0
            
            # Check if device exists
            device = cam['device']
            device_exists = os.path.exists(device)
            
            status_list.append({
                "camera_id": cam['id'],
                "name": cam['name'],
                "device": device,
                "port": port,
                "running": is_running,
                "device_exists": device_exists,
                "url": cam['url']
            })
        
        return {
            "status": "success",
            "cameras": status_list
        }
        
    except Exception as e:
        logger.error(f"Error getting camera status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =========================================================================
# Robot Camera SSH Control (for StatusJetson UI)
# =========================================================================

ROBOT_SSH_USER = "lrt_geeokom"
ROBOT_SSH_HOST = "192.168.2.50"
ROBOT_SSH_PASS = "qwerty"


@router.post("/robot_cameras/start/{index}")
async def start_robot_camera(index: int) -> dict[str, object]:
    """Start mjpg_streamer for a specific robot camera in a screen session via SSH."""
    if index < 0 or index >= len(ROBOT_CAMERAS):
        raise HTTPException(status_code=404, detail=f"Camera index {index} out of range (0-{len(ROBOT_CAMERAS)-1})")

    cam = ROBOT_CAMERAS[index]
    port = cam["port"]
    device = cam["device"]
    session = _camera_screen_name(port)

    # Kill any existing screen session / port holder first
    kill_cmd = (
        f"screen -S {session} -X quit 2>/dev/null; "
        f"fuser -k -n tcp {port} 2>/dev/null; "
        f"pkill -f \"gst-launch-1.0.*{device}\" 2>/dev/null || true; "
        f"pkill -f \"mjpg_streamer.*{device}\" 2>/dev/null || true; "
        f"sleep 1"
    )

    # Start mjpg_streamer inside a detached screen session with -y -q 50
    streamer_cmd = (
        f"mjpg_streamer "
        f"-i \\\"input_uvc.so -d {device} -r 640x480 -f 15 -y -q 50\\\" "
        f"-o \\\"output_http.so -p {port}\\\""
    )
    start_cmd = f"screen -dmS {session} bash -lc '{streamer_cmd}'"

    full_cmd = f"{kill_cmd} && {start_cmd}"

    ssh_cmd = [
        "sshpass", "-p", ROBOT_SSH_PASS,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
        f"{ROBOT_SSH_USER}@{ROBOT_SSH_HOST}",
        full_cmd
    ]

    try:
        result = subprocess.run(ssh_cmd, timeout=15, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if result.returncode == 0:
            logger.info(f"Started robot camera {index} ({cam['name']}) screen={session} port={port}")
            return {
                "status": "success",
                "message": f"Camera {cam['name']} started (screen {session}, port {port})",
                "index": index,
                "port": port,
                "screen_session": session,
            }
        else:
            raise HTTPException(status_code=500, detail=f"SSH command failed: {result.stdout}")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="SSH connection timeout")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="sshpass not installed")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting robot camera {index}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/robot_cameras/stop/{index}")
async def stop_robot_camera(index: int) -> dict[str, object]:
    """Stop a robot camera by killing its screen session via SSH."""
    if index < 0 or index >= len(ROBOT_CAMERAS):
        raise HTTPException(status_code=404, detail=f"Camera index {index} out of range")

    cam = ROBOT_CAMERAS[index]
    port = cam["port"]
    session = _camera_screen_name(port)

    device = cam.get("device", "")
    pkill_cmd = ""
    if device:
        pkill_cmd = (
            f"pkill -f \"gst-launch-1.0.*{device}\" 2>/dev/null || true; "
            f"pkill -f \"mjpg_streamer.*{device}\" 2>/dev/null || true; "
        )

    kill_cmd = (
        f"screen -S {session} -X quit 2>/dev/null; "
        f"fuser -k -n tcp {port} 2>/dev/null || true; "
        f"{pkill_cmd}"
    )

    ssh_cmd = [
        "sshpass", "-p", ROBOT_SSH_PASS,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=5",
        f"{ROBOT_SSH_USER}@{ROBOT_SSH_HOST}",
        kill_cmd
    ]

    try:
        subprocess.run(ssh_cmd, timeout=10, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info(f"Stopped robot camera {index} ({cam['name']}) screen={session} port={port}")
        return {
            "status": "success",
            "message": f"Camera {cam['name']} stopped (screen {session})",
            "index": index,
            "port": port,
            "screen_session": session,
        }
    except Exception as e:
        logger.error(f"Error stopping robot camera {index}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/robot_cameras/status")
async def get_robot_cameras_status() -> dict[str, object]:
    """Check which robot cameras are currently running via SSH (screen sessions)."""
    # Build a single SSH command that checks all screen sessions at once
    screen_checks = []
    for cam in ROBOT_CAMERAS:
        port = cam["port"]
        session = _camera_screen_name(port)
        screen_checks.append(
            f"(screen -ls {session} 2>/dev/null | grep -q {session} "
            f"&& echo 'CAM_{session}=RUNNING' || echo 'CAM_{session}=STOPPED')"
        )

    combined_cmd = " && ".join(screen_checks)

    ssh_cmd = [
        "sshpass", "-p", ROBOT_SSH_PASS,
        "ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=3",
        f"{ROBOT_SSH_USER}@{ROBOT_SSH_HOST}",
        combined_cmd
    ]

    statuses = {}
    for i, cam in enumerate(ROBOT_CAMERAS):
        session = _camera_screen_name(cam["port"])
        statuses[i] = {
            "running": False,
            "name": cam["name"],
            "port": cam["port"],
            "screen_session": session,
        }

    try:
        result = subprocess.run(ssh_cmd, timeout=8, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        if result.returncode == 0:
            for i, cam in enumerate(ROBOT_CAMERAS):
                session = _camera_screen_name(cam["port"])
                if f"CAM_{session}=RUNNING" in result.stdout:
                    statuses[i]["running"] = True
    except Exception as e:
        logger.error(f"Error checking robot camera status: {e}")

    return {"cameras": statuses}


@router.post("/robot_cameras/start_all")
async def start_all_robot_cameras() -> dict[str, object]:
    """Start all robot cameras via SSH screen sessions."""
    results = []
    for i in range(len(ROBOT_CAMERAS)):
        try:
            res = await start_robot_camera(i)
            results.append(res)
        except HTTPException as e:
            results.append({"status": "error", "index": i, "detail": e.detail})
    return {"status": "success", "cameras": results}


@router.post("/robot_cameras/stop_all")
async def stop_all_robot_cameras() -> dict[str, object]:
    """Stop all robot cameras via SSH screen sessions."""
    results = []
    for i in range(len(ROBOT_CAMERAS)):
        try:
            res = await stop_robot_camera(i)
            results.append(res)
        except HTTPException as e:
            results.append({"status": "error", "index": i, "detail": e.detail})
    return {"status": "success", "cameras": results}
