import logging
import shlex
import subprocess
import re
import os
import shutil
import signal
import time
from pathlib import Path

logger = logging.getLogger(__name__)

LOCAL_CMD_TIMEOUT_S = 5
SSH_CMD_TIMEOUT_S = 6

V4L2_TO_GST_RAW_FORMAT = {
    "YUYV": "YUY2",
    "YUY2": "YUY2",
    "UYVY": "UYVY",
    "NV12": "NV12",
    "YU12": "I420",
    "YV12": "YV12",
    "GREY": "GRAY8",
    "RGB3": "RGB",
    "BGR3": "BGR",
}

COMPRESSED_MJPEG_CODES = {"MJPG", "JPEG"}
COMPRESSED_H264_CODES = {"H264"}
YUY2_CODES = {"YUYV", "YUY2"}


class CameraController:
    """Manage GStreamer sender/receiver pipelines using named screen sessions."""

    def __init__(self):
        self.runtime_dir = Path(__file__).resolve().parent.parent / "logs" / "vision_runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.remote_runtime_dir = "${HOME}/.vision_app_runtime"
        self._status_cache: dict[str, object] = {
            "expires_at": 0.0,
            "values": {},
        }

    @staticmethod
    def _process_name(kind: str, cam_id: str) -> str:
        return f"cam_{kind}_{cam_id}"

    @staticmethod
    def _session_is_live(screen_output: str, session_name: str) -> bool:
        # Match only valid attached/detached entries. Ignore "(Dead ???)" records.
        pattern = re.compile(rf"\b\d+\.{re.escape(session_name)}\b.*\((Detached|Attached)\)", re.IGNORECASE)
        return bool(pattern.search(screen_output))

    def _log_file(self, kind: str, cam_id: str) -> Path:
        return self.runtime_dir / f"{self._process_name(kind, cam_id)}.log"

    def _pid_file(self, kind: str, cam_id: str) -> Path:
        return self.runtime_dir / f"{self._process_name(kind, cam_id)}.pid"

    def _remote_log_file(self, kind: str, cam_id: str) -> str:
        return f"{self.remote_runtime_dir}/{self._process_name(kind, cam_id)}.log"

    def _remote_process_marker(self, kind: str, cam_id: str) -> str:
        return f"VISION_CAM_SESSION={self._process_name(kind, cam_id)}"

    @staticmethod
    def _wrap_remote_bash(command: str) -> str:
        # Ensure predictable PATH/TERM for non-interactive SSH sessions.
        prelude = 'export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:$PATH"; export TERM="xterm"; '
        return f"bash -lc {shlex.quote(prelude + command)}"

    @staticmethod
    def _is_ssh_config(config: dict) -> bool:
        return str(config.get("execution_mode", "local")).lower() == "ssh"

    def _runtime_config(self, kind: str, config: dict) -> dict:
        runtime_config = dict(config)
        if kind == "recv":
            runtime_config["execution_mode"] = "local"
        return runtime_config

    @staticmethod
    def _ssh_target(config: dict) -> str:
        return f"{config.get('ssh_user')}@{config.get('ssh_host')}"

    def _ssh_base_command(self, config: dict) -> list[str]:
        return [
            "sshpass",
            "-p",
            str(config.get("ssh_password", "")),
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "BatchMode=no",
            "-o",
            "ConnectionAttempts=1",
            "-o",
            "ConnectTimeout=2",
            "-p",
            str(config.get("ssh_port", 22)),
            self._ssh_target(config),
        ]

    def _command_timeout(self, config: dict) -> int:
        return SSH_CMD_TIMEOUT_S if self._is_ssh_config(config) else LOCAL_CMD_TIMEOUT_S

    @staticmethod
    def _cache_key(cam_id: str, kind: str) -> str:
        return f"{cam_id}:{kind}"

    def _clear_status_cache(self):
        self._status_cache["expires_at"] = 0.0
        self._status_cache["values"] = {}

    def _get_cached_status(self, cam_id: str, kind: str) -> bool | None:
        if time.monotonic() >= float(self._status_cache.get("expires_at", 0.0)):
            return None
        values = self._status_cache.get("values", {})
        cached = values.get(self._cache_key(cam_id, kind))
        if cached is None:
            return None
        return bool(cached)

    def _set_cached_status(self, cam_id: str, kind: str, is_running: bool):
        values = dict(self._status_cache.get("values", {}))
        values[self._cache_key(cam_id, kind)] = bool(is_running)
        self._status_cache["values"] = values

    def _warm_status_cache(self, status_map: dict[str, bool], ttl_s: float):
        self._status_cache["expires_at"] = time.monotonic() + ttl_s
        self._status_cache["values"] = dict(status_map)

    def _group_ssh_configs(self, camera_configs: dict) -> dict[tuple[str, int, str, str], list[tuple[str, dict]]]:
        grouped: dict[tuple[str, int, str, str], list[tuple[str, dict]]] = {}
        for cam_id, config in camera_configs.items():
            if not self._is_ssh_config(config):
                continue
            key = (
                str(config.get("ssh_host", "")),
                int(config.get("ssh_port", 22)),
                str(config.get("ssh_user", "")),
                str(config.get("ssh_password", "")),
            )
            grouped.setdefault(key, []).append((cam_id, config))
        return grouped

    def _batch_fetch_ssh_screen_statuses(self, camera_configs: dict) -> dict[str, bool]:
        status_map: dict[str, bool] = {}
        grouped = self._group_ssh_configs(camera_configs)
        for cameras in grouped.values():
            session_names = []
            for cam_id, _config in cameras:
                session_names.append(self._process_name("send", cam_id))
                session_names.append(self._process_name("recv", cam_id))

            if not session_names:
                continue

            remote_command = self._wrap_remote_bash("screen -ls | cat")
            command = self._ssh_base_command(cameras[0][1]) + [remote_command]
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self._command_timeout(cameras[0][1]),
                )
                output = f"{result.stdout}\n{result.stderr}"
            except subprocess.TimeoutExpired:
                logger.warning("Timed out fetching batched vision screen statuses")
                output = ""
            except FileNotFoundError:
                logger.warning("sshpass is not installed on the backend host")
                output = ""

            for cam_id, _config in cameras:
                sender_session = self._process_name("send", cam_id)
                receiver_session = self._process_name("recv", cam_id)
                status_map[self._cache_key(cam_id, "send")] = self._session_is_live(output, sender_session)
                status_map[self._cache_key(cam_id, "recv")] = self._session_is_live(output, receiver_session)
        return status_map

    def _is_process_running(self, kind: str, cam_id: str, config: dict) -> bool:
        config = self._runtime_config(kind, config)
        if kind == "send":
            return self.is_sender_running(cam_id, config)
        return self.is_receiver_running(cam_id, config)

    def _wait_for_process_state(self, kind: str, cam_id: str, config: dict, should_run: bool) -> bool:
        config = self._runtime_config(kind, config)
        if self._is_ssh_config(config):
            # screen -dmS returns as soon as the session is detached; give the
            # remote a moment to register it, then do a single definitive check.
            time.sleep(1.5)
            return self._is_process_running(kind, cam_id, config) == should_run
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            if self._is_process_running(kind, cam_id, config) == should_run:
                return True
            time.sleep(0.25)
        return self._is_process_running(kind, cam_id, config) == should_run

    def _screen_session_exists(self, kind: str, cam_id: str, config: dict) -> bool:
        session_name = self._process_name(kind, cam_id)
        if self._is_ssh_config(config):
            command = self._ssh_base_command(config) + [self._wrap_remote_bash("screen -ls | cat")]
        else:
            if not shutil.which("screen"):
                logger.warning("screen is not installed on the backend host")
                return False
            command = ["screen", "-ls"]

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self._command_timeout(config),
            )
        except subprocess.TimeoutExpired:
            logger.warning("Timed out checking %s session for camera %s", kind, cam_id)
            return False
        except FileNotFoundError:
            if self._is_ssh_config(config):
                logger.warning("sshpass is not installed on the backend host")
            else:
                logger.warning("screen is not installed on the backend host")
            return False

        output = f"{result.stdout}\n{result.stderr}"
        return self._session_is_live(output, session_name)

    def _read_process_log_tail(self, kind: str, cam_id: str, config: dict, lines: int = 40) -> str:
        config = self._runtime_config(kind, config)
        if self._is_ssh_config(config):
            remote_log_file = self._remote_log_file(kind, cam_id)
            command = self._ssh_base_command(config) + [
                self._wrap_remote_bash(
                    f"tail -n {int(lines)} {remote_log_file} 2>/dev/null || true"
                )
            ]
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self._command_timeout(config),
                )
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return ""

            return (result.stdout or result.stderr or "").strip()

        log_path = self._log_file(kind, cam_id)
        if not log_path.exists():
            return ""

        try:
            log_text = log_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

        return "\n".join(log_text.splitlines()[-lines:]).strip()

    def _start_failure_error(self, kind: str, cam_id: str, config: dict) -> RuntimeError:
        label = "Sender" if kind == "send" else "Receiver"
        log_tail = self._read_process_log_tail(kind, cam_id, config)
        if log_tail:
            return RuntimeError(f"{label} failed to start for camera {cam_id}. Recent log output:\n{log_tail}")
        return RuntimeError(f"{label} failed to start for camera {cam_id}")

    def _read_pid(self, kind: str, cam_id: str) -> int | None:
        pid_file = self._pid_file(kind, cam_id)
        if not pid_file.exists():
            return None
        try:
            return int(pid_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            return None

    def _write_pid(self, kind: str, cam_id: str, pid: int):
        self._pid_file(kind, cam_id).write_text(str(pid), encoding="utf-8")

    def _clear_pid(self, kind: str, cam_id: str):
        try:
            self._pid_file(kind, cam_id).unlink(missing_ok=True)
        except OSError:
            pass

    @staticmethod
    def _is_pid_live(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    @staticmethod
    def _safe_kill(pid: int, sig: int):
        try:
            os.kill(pid, sig)
        except OSError:
            pass

    @staticmethod
    def _safe_kill_process_group(pid: int, sig: int):
        """Kill the whole process group for a launched local pipeline.

        Local commands are started with start_new_session=True, so the launcher
        shell and gst child process share an isolated process group.
        """
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, sig)
            return
        except OSError:
            pass
        try:
            os.kill(pid, sig)
        except OSError:
            pass

    def _find_local_pids(self, kind: str, cam_id: str, config: dict) -> list[int]:
        device = str(config.get("device", "/dev/video0"))
        port = str(config.get("target_port", 2140))
        session_marker = self._process_name(kind, cam_id)

        try:
            result = subprocess.run(
                ["ps", "-eo", "pid=,args="],
                check=False,
                capture_output=True,
                text=True,
                timeout=LOCAL_CMD_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            return []

        tagged_pids: list[int] = []
        legacy_pids: list[int] = []
        for line in result.stdout.splitlines():
            row = line.strip()
            if not row:
                continue
            if "gst-launch-1.0" not in row:
                continue
            if f"port={port}" not in row:
                continue
            if kind == "send" and f"device={device}" not in row:
                continue
            if kind == "recv" and "udpsrc" not in row:
                continue
            parts = row.split(None, 1)
            if not parts:
                continue
            try:
                pid = int(parts[0])
            except ValueError:
                continue

            if f"VISION_CAM_SESSION={session_marker}" in row:
                tagged_pids.append(pid)
            else:
                legacy_pids.append(pid)

        # Keep tagged first, but include legacy matches to avoid leaving stale gst
        # children behind if only the launcher shell carried the marker.
        return list(dict.fromkeys(tagged_pids + legacy_pids))

    def _run_command_for_config(self, config: dict, shell_command: str, timeout_s: int | None = None) -> subprocess.CompletedProcess:
        timeout = timeout_s if timeout_s is not None else self._command_timeout(config)
        if self._is_ssh_config(config):
            command = self._ssh_base_command(config) + [self._wrap_remote_bash(shell_command)]
            return subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

        return subprocess.run(
            ["bash", "-lc", shell_command],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    def _release_v4l2_device_owners(self, config: dict, device: str, cam_id: str):
        """Best-effort cleanup of stale processes that still hold a camera node.

        This avoids retry loops failing with "Device ... is busy" after a failed
        pipeline launch or stale process leftovers.
        """
        q_device = shlex.quote(str(device))
        release_cmd = (
            f"pkill -TERM -f {shlex.quote(f'device={device}')} >/dev/null 2>&1 || true; "
            f"pkill -TERM -f {shlex.quote(f'-d {device}')} >/dev/null 2>&1 || true; "
            "sleep 0.3; "
            f"pkill -KILL -f {shlex.quote(f'device={device}')} >/dev/null 2>&1 || true; "
            f"pkill -KILL -f {shlex.quote(f'-d {device}')} >/dev/null 2>&1 || true; "
            f"fuser -v {q_device} 2>/dev/null || true"
        )
        try:
            result = self._run_command_for_config(config, release_cmd, timeout_s=6)
            details = "\n".join(
                part.strip()
                for part in (result.stdout or "", result.stderr or "")
                if part and part.strip()
            )
            if details:
                logger.info("Device owner cleanup for %s (%s): %s", cam_id, device, details)
        except Exception as exc:
            logger.warning("Failed to cleanup owners for %s (%s): %s", cam_id, device, exc)

    @staticmethod
    def _extract_v4l2_pixfmts(probe_output: str) -> list[str]:
        pixfmts: list[str] = []
        # Typical lines contain a FOURCC in single quotes, e.g. "'MJPG'".
        for match in re.finditer(r"'([A-Z0-9]{4})'", (probe_output or "").upper()):
            code = match.group(1)
            if code not in pixfmts:
                pixfmts.append(code)
        return pixfmts

    def _probe_v4l2_source_caps(self, config: dict, device: str) -> tuple[str, str, list[str]]:
        """Return detected source format family and probe output for diagnostics.

        Format family is one of: h264, mjpeg, yuy2, raw.
        """
        escaped_device = shlex.quote(str(device))
        probe_cmd = (
            f"v4l2-ctl --device={escaped_device} --list-formats-ext 2>&1 "
            f"|| v4l2-ctl --device={escaped_device} --list-formats 2>&1"
        )

        try:
            result = self._run_command_for_config(config, probe_cmd, timeout_s=8)
            output = f"{result.stdout or ''}\n{result.stderr or ''}"
        except FileNotFoundError:
            logger.warning("v4l2 probe skipped for %s: helper tool missing", device)
            return "raw", "", []
        except subprocess.TimeoutExpired:
            logger.warning("v4l2 probe timed out for %s", device)
            return "raw", "", []
        except Exception as exc:
            logger.warning("v4l2 probe failed for %s: %s", device, exc)
            return "raw", "", []

        pixfmts = self._extract_v4l2_pixfmts(output)
        normalized = output.upper()
        if "H264" in normalized or "X264" in normalized:
            return "h264", output, pixfmts
        if "MJPG" in normalized or "MJPEG" in normalized or "JPEG" in normalized:
            return "mjpeg", output, pixfmts
        if "YUYV" in normalized or "YUY2" in normalized:
            return "yuy2", output, pixfmts
        return "raw", output, pixfmts

    @staticmethod
    def _quote_pipeline_value(value: object) -> str:
        return shlex.quote(str(value))

    def _build_sender_pipeline_for_mode(self, mode: str, config: dict, raw_format: str | None = None) -> tuple[str, str]:
        device = config.get("device", "/dev/video0")
        width = int(config.get("width", 1280))
        height = int(config.get("height", 720))
        framerate = int(config.get("framerate", 24))
        bitrate = int(config.get("bitrate", 512))
        crop_top = int(config.get("crop_top", 0))
        crop_bottom = int(config.get("crop_bottom", 0))
        crop_left = int(config.get("crop_left", 0))
        crop_right = int(config.get("crop_right", 0))
        mirror_horizontal = bool(config.get("mirror_horizontal", False))
        rotation = int(config.get("rotation", 0))
        force_software = bool(config.get("force_software_transcode", True))
        host = config.get("target_ip", "127.0.0.1")
        port = int(config.get("target_port", 2140))

        source_note = f"source format={mode}"
        if raw_format:
            source_note += f"/{raw_format}"

        q_device = self._quote_pipeline_value(device)
        q_host = self._quote_pipeline_value(host)

        if mode == "h264" and not force_software:
            pipeline = (
                f"gst-launch-1.0 -e v4l2src device={q_device} ! "
                "video/x-h264 ! "
                "h264parse config-interval=-1 ! "
                f"rtph264pay config-interval=1 pt=96 ! udpsink host={q_host} port={port}"
            )
            source_note += " (passthrough)"
            return pipeline, source_note

        pre_convert = "v4l2src device={device} ! ".format(device=q_device)
        if mode == "h264":
            # Do not force stream-format here; different cameras expose avc/byte-stream.
            pre_convert += "video/x-h264 ! h264parse ! avdec_h264 ! "
        elif mode == "mjpeg":
            # Keep source caps permissive and scale later so custom output
            # resolutions don't fail source negotiation on strict drivers.
            pre_convert += (
                "image/jpeg ! "
                "jpegparse ! jpegdec ! "
            )
        elif mode == "yuy2":
            if force_software:
                pre_convert += "video/x-raw,format=YUY2 ! "
            else:
                pre_convert += (
                    "video/x-raw,format=YUY2 ! "
                )
        elif mode == "raw" and raw_format:
            pre_convert += f"video/x-raw,format={raw_format} ! "

        rotation_stage = ""
        if rotation == 90:
            rotation_stage = "videoflip video-direction=90r ! "
        elif rotation == 180:
            rotation_stage = "videoflip video-direction=180 ! "
        elif rotation == 270:
            rotation_stage = "videoflip video-direction=90l ! "

        mirror_stage = "videoflip video-direction=horizontal-flip ! " if mirror_horizontal else ""

        pipeline = (
            f"gst-launch-1.0 -e {pre_convert}"
            "videoconvert ! videoscale ! videorate ! "
            f"video/x-raw,width={width},height={height},framerate={framerate}/1 ! "
            f"{rotation_stage}{mirror_stage}"
            f"videocrop top={crop_top} bottom={crop_bottom} left={crop_left} right={crop_right} ! "
            f"x264enc tune=zerolatency speed-preset=ultrafast bitrate={bitrate} ! "
            "h264parse config-interval=-1 ! "
            f"rtph264pay config-interval=1 pt=96 ! udpsink host={q_host} port={port}"
        )

        return pipeline, source_note

    def _build_source_probe_pipeline(self, mode: str, config: dict, raw_format: str | None = None) -> str | None:
        """Build a lightweight pipeline used only to validate source caps negotiation."""
        device = config.get("device", "/dev/video0")
        q_device = self._quote_pipeline_value(device)

        if mode == "h264":
            return (
                f"gst-launch-1.0 -q -e v4l2src device={q_device} num-buffers=2 ! "
                "video/x-h264 ! "
                "h264parse ! fakesink sync=false"
            )
        if mode == "mjpeg":
            return (
                f"gst-launch-1.0 -q -e v4l2src device={q_device} num-buffers=2 ! "
                "image/jpeg ! "
                "jpegparse ! fakesink sync=false"
            )
        if mode == "yuy2":
            return (
                f"gst-launch-1.0 -q -e v4l2src device={q_device} num-buffers=2 ! "
                "video/x-raw,format=YUY2 ! "
                "fakesink sync=false"
            )
        if mode == "raw" and raw_format:
            return (
                f"gst-launch-1.0 -q -e v4l2src device={q_device} num-buffers=2 ! "
                f"video/x-raw,format={raw_format} ! "
                "fakesink sync=false"
            )
        if mode == "raw":
            return (
                f"gst-launch-1.0 -q -e v4l2src device={q_device} num-buffers=2 ! "
                "video/x-raw ! fakesink sync=false"
            )
        return None

    def _source_mode_is_negotiable(self, config: dict, cam_id: str, mode: str, raw_format: str | None = None) -> bool:
        probe_pipeline = self._build_source_probe_pipeline(mode, config, raw_format=raw_format)
        if not probe_pipeline:
            return True
        try:
            result = self._run_command_for_config(config, probe_pipeline, timeout_s=4)
        except Exception as exc:
            logger.warning(
                "Source probe failed for %s (%s/%s): %s",
                cam_id,
                mode,
                raw_format or "default",
                exc,
            )
            return False

        if result.returncode == 0:
            return True

        details = "\n".join(
            part.strip()
            for part in (result.stdout or "", result.stderr or "")
            if part and part.strip()
        )
        logger.info(
            "Source probe rejected for %s (%s/%s): %s",
            cam_id,
            mode,
            raw_format or "default",
            details or f"exit={result.returncode}",
        )
        return False

    def _build_sender_pipeline_candidates(self, cam_id: str, config: dict) -> list[tuple[str, str]]:
        device = config.get("device", "/dev/video0")
        detected_mode, probe_output, pixfmts = self._probe_v4l2_source_caps(config, str(device))
        selected_mode = str(config.get("source_format", "auto")).strip().lower()
        force_software = bool(config.get("force_software_transcode", True))
        if probe_output:
            logger.info("Camera %s v4l2 probe output:\n%s", cam_id, probe_output.strip())
        if pixfmts:
            logger.info("Camera %s v4l2 detected pixel formats: %s", cam_id, ", ".join(pixfmts))

        raw_formats: list[str] = []
        for pixfmt in pixfmts:
            gst_raw = V4L2_TO_GST_RAW_FORMAT.get(pixfmt)
            if gst_raw and gst_raw not in raw_formats:
                raw_formats.append(gst_raw)

        pixfmt_set = set(pixfmts)
        supports_h264 = bool(pixfmt_set & COMPRESSED_H264_CODES)
        supports_mjpeg = bool(pixfmt_set & COMPRESSED_MJPEG_CODES)
        supports_yuy2 = bool(pixfmt_set & YUY2_CODES)

        if selected_mode and selected_mode != "auto":
            preferred_order = [selected_mode]
        else:
            preferred_order = [detected_mode]
            if supports_h264:
                preferred_order.append("h264")
            if supports_mjpeg:
                preferred_order.append("mjpeg")
            if supports_yuy2:
                preferred_order.append("yuy2")
            # Only try generic raw mode when the device reports raw-capable formats.
            if raw_formats:
                preferred_order.append("raw")
            if len(preferred_order) == 1:
                preferred_order.extend(["h264", "mjpeg", "yuy2", "raw"])
        ordered_modes: list[str] = []
        for mode in preferred_order:
            if mode not in ordered_modes:
                ordered_modes.append(mode)

        candidate_entries: list[tuple[str, str, str, str | None]] = []
        for mode in ordered_modes:
            mode_variants = [(mode, None)]
            # For raw fallback, explicitly try probed raw formats to avoid drivers
            # picking an incompatible default (e.g. depth-only or unsupported raw).
            if mode == "raw" and raw_formats:
                mode_variants = [(mode, raw_format) for raw_format in raw_formats] + mode_variants

            for variant_mode, raw_format in mode_variants:
                pipeline, note = self._build_sender_pipeline_for_mode(variant_mode, config, raw_format=raw_format)
                auto_note = (
                    f"requested={selected_mode}; detected={detected_mode}; trying {variant_mode}; "
                    f"software_override={force_software}"
                )
                candidate_entries.append((pipeline, f"{note}; {auto_note}", variant_mode, raw_format))

        # In auto mode, prioritize candidates that pass a fast source-only
        # negotiation check so we avoid expensive full-pipeline retries.
        if selected_mode == "auto" and candidate_entries:
            known_probe_results: dict[tuple[str, str | None], bool] = {}
            viable: list[tuple[str, str, str, str | None]] = []
            non_viable: list[tuple[str, str, str, str | None]] = []
            for entry in candidate_entries:
                _pipeline, _note, mode, raw_format = entry
                key = (mode, raw_format)
                if key not in known_probe_results:
                    known_probe_results[key] = self._source_mode_is_negotiable(config, cam_id, mode, raw_format=raw_format)
                if known_probe_results[key]:
                    viable.append(entry)
                else:
                    non_viable.append(entry)
            candidate_entries = viable + non_viable

        return [(pipeline, note) for pipeline, note, _mode, _raw in candidate_entries]

    def _stop_local_pid_process(self, kind: str, cam_id: str):
        pid = self._read_pid(kind, cam_id)
        if pid is None:
            return

        if self._is_pid_live(pid):
            self._safe_kill_process_group(pid, signal.SIGTERM)
            time.sleep(0.2)
            if self._is_pid_live(pid):
                self._safe_kill_process_group(pid, signal.SIGKILL)

        self._clear_pid(kind, cam_id)

    def _launch_process(self, kind: str, cam_id: str, pipeline: str, config: dict):
        self._clear_status_cache()
        session_name = self._process_name(kind, cam_id)
        if self._is_ssh_config(config):
            log_path = self._remote_log_file(kind, cam_id)
            process_marker = self._remote_process_marker(kind, cam_id)
            remote_command = self._wrap_remote_bash(
                "if ! command -v screen >/dev/null 2>&1; then "
                "echo 'screen is not installed on remote host' >&2; exit 127; fi; "
                f"screen -S {shlex.quote(session_name)} -X quit >/dev/null 2>&1 || true; "
                "screen -wipe >/dev/null 2>&1 || true; "
                f"mkdir -p {self.remote_runtime_dir} && "
                f"screen -L -Logfile {log_path} -dmS {shlex.quote(session_name)} "
                f"bash -lc {shlex.quote(f'{process_marker} {pipeline}')}"
            )
            command = self._ssh_base_command(config) + [remote_command]
        else:
            log_path = self._log_file(kind, cam_id)
            session_marker = self._process_name(kind, cam_id)
            try:
                with open(log_path, "ab") as log_fp:
                    proc = subprocess.Popen(
                        ["bash", "-lc", f"VISION_CAM_SESSION={shlex.quote(session_marker)} {pipeline}"],
                        stdout=log_fp,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
            except OSError as exc:
                raise RuntimeError(f"Failed launching {kind} process for camera {cam_id}: {exc}") from exc
            self._write_pid(kind, cam_id, proc.pid)
            return

        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=self._is_ssh_config(config),
                text=self._is_ssh_config(config),
                timeout=self._command_timeout(config),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Timed out launching {kind} process for camera {cam_id}") from exc
        except FileNotFoundError as exc:
            if self._is_ssh_config(config):
                raise RuntimeError("sshpass is not installed on the backend host") from exc
            raise RuntimeError(f"Failed launching {kind} process for camera {cam_id}: {exc}") from exc

        if self._is_ssh_config(config) and result.returncode != 0:
            details = "\n".join(
                part.strip()
                for part in (result.stdout or "", result.stderr or "")
                if part and part.strip()
            )
            raise RuntimeError(
                f"SSH launch command failed for camera {cam_id}: {details or 'unknown SSH error'}"
            )
            
    def _stop_process(self, kind: str, cam_id: str, config: dict):
        config = self._runtime_config(kind, config)
        self._clear_status_cache()
        # Always stop any locally-running process first.
        # This ensures a previous local sender is killed when switching to SSH mode.
        self._stop_local_pid_process(kind, cam_id)

        orphan_pids = self._find_local_pids(kind, cam_id, config)
        for pid in orphan_pids:
            self._safe_kill(pid, signal.SIGTERM)
        if orphan_pids:
            time.sleep(0.2)
        for pid in orphan_pids:
            if self._is_pid_live(pid):
                self._safe_kill(pid, signal.SIGKILL)

        if not self._is_ssh_config(config):
            return

        # SSH mode: also stop the remote screen session.
        session_name = self._process_name(kind, cam_id)
        process_marker = self._remote_process_marker(kind, cam_id)

        def _remote_kill_by_marker():
            # Kill any orphan remote gst process that survived detached from screen.
            kill_cmd = (
                f"pkill -TERM -f {shlex.quote(process_marker)} >/dev/null 2>&1 || true; "
                "sleep 0.2; "
                f"pkill -KILL -f {shlex.quote(process_marker)} >/dev/null 2>&1 || true"
            )
            command = self._ssh_base_command(config) + [self._wrap_remote_bash(kill_cmd)]
            try:
                subprocess.run(command, check=False, timeout=self._command_timeout(config))
            except subprocess.TimeoutExpired:
                logger.warning("Timed out killing orphan %s process for camera %s", kind, cam_id)

        if not self._screen_session_exists(kind, cam_id, config):
            logger.info("No live %s process recorded for %s", kind, cam_id)
            # Clean stale records to avoid false-positive status later.
            command = self._ssh_base_command(config) + [self._wrap_remote_bash("screen -wipe >/dev/null 2>&1 || true")]
            try:
                subprocess.run(command, check=False, timeout=self._command_timeout(config))
            except subprocess.TimeoutExpired:
                logger.warning("Timed out wiping dead %s sessions for camera %s", kind, cam_id)
            _remote_kill_by_marker()
            return

        command = self._ssh_base_command(config) + [
            self._wrap_remote_bash(f"screen -S {shlex.quote(session_name)} -X quit")
        ]
        try:
            subprocess.run(command, check=False, timeout=self._command_timeout(config))
        except subprocess.TimeoutExpired:
            logger.warning("Timed out stopping %s process for camera %s", kind, cam_id)

        _remote_kill_by_marker()

        # Wipe dead sessions after stop to keep status detection clean.
        wipe_command = self._ssh_base_command(config) + [
            self._wrap_remote_bash("screen -wipe >/dev/null 2>&1 || true")
        ]
        try:
            subprocess.run(wipe_command, check=False, timeout=self._command_timeout(config))
        except subprocess.TimeoutExpired:
            logger.warning("Timed out wiping dead %s sessions for camera %s", kind, cam_id)

    def is_sender_running(self, cam_id: str, config: dict) -> bool:
        config = self._runtime_config("send", config)
        cached = self._get_cached_status(cam_id, "send")
        if cached is not None:
            return cached
        if self._screen_session_exists("send", cam_id, config):
            self._set_cached_status(cam_id, "send", True)
            return True
        if not self._is_ssh_config(config):
            pid = self._read_pid("send", cam_id)
            if pid is not None and self._is_pid_live(pid):
                self._set_cached_status(cam_id, "send", True)
                return True
            if self._find_local_pids("send", cam_id, config):
                self._set_cached_status(cam_id, "send", True)
                return True
        self._set_cached_status(cam_id, "send", False)
        return False

    def is_receiver_running(self, cam_id: str, config: dict) -> bool:
        config = self._runtime_config("recv", config)
        cached = self._get_cached_status(cam_id, "recv")
        if cached is not None:
            return cached
        if self._screen_session_exists("recv", cam_id, config):
            self._set_cached_status(cam_id, "recv", True)
            return True
        if not self._is_ssh_config(config):
            pid = self._read_pid("recv", cam_id)
            if pid is not None and self._is_pid_live(pid):
                self._set_cached_status(cam_id, "recv", True)
                return True
            if self._find_local_pids("recv", cam_id, config):
                self._set_cached_status(cam_id, "recv", True)
                return True
        self._set_cached_status(cam_id, "recv", False)
        return False

    def sync_statuses(self, camera_configs: dict, force: bool = False) -> dict:
        if force:
            self._clear_status_cache()

        if not force and time.monotonic() < float(self._status_cache.get("expires_at", 0.0)):
            for cam_id, config in camera_configs.items():
                config["sender_running"] = bool(self._status_cache["values"].get(self._cache_key(cam_id, "send"), False))
                config["receiver_running"] = bool(self._status_cache["values"].get(self._cache_key(cam_id, "recv"), False))
            return camera_configs

        status_map = self._batch_fetch_ssh_screen_statuses(camera_configs)
        for cam_id, config in camera_configs.items():
            sender_key = self._cache_key(cam_id, "send")
            receiver_key = self._cache_key(cam_id, "recv")
            if sender_key in status_map:
                config["sender_running"] = bool(status_map[sender_key])
            else:
                config["sender_running"] = self.is_sender_running(cam_id, config)
                status_map[sender_key] = bool(config["sender_running"])

            if receiver_key in status_map:
                config["receiver_running"] = bool(status_map[receiver_key])
            else:
                config["receiver_running"] = self.is_receiver_running(cam_id, config)
                status_map[receiver_key] = bool(config["receiver_running"])

        self._warm_status_cache(status_map, ttl_s=1.5)
        return camera_configs

    def start_sender(self, cam_id: str, config: dict):
        runtime_config = self._runtime_config("send", config)
        self.stop_sender(cam_id, config)
        self._release_v4l2_device_owners(runtime_config, str(config.get("device", "/dev/video0")), cam_id)

        errors: list[str] = []
        candidates = self._build_sender_pipeline_candidates(cam_id, config)
        for pipeline, mode_note in candidates:
            logger.info("Starting sender for %s (%s): %s", cam_id, mode_note, pipeline)
            try:
                self._launch_process("send", cam_id, pipeline, runtime_config)
                # For SSH/screen launches verify the session came up; for local Popen success is enough.
                if self._is_ssh_config(runtime_config):
                    if not self._wait_for_process_state("send", cam_id, runtime_config, True):
                        raise self._start_failure_error("send", cam_id, runtime_config)
                return
            except Exception as exc:
                errors.append(f"{mode_note}: {exc}")
                logger.warning("Sender start attempt failed for %s (%s): %s", cam_id, mode_note, exc)
                # Ensure failed attempt is fully cleaned before trying next pipeline.
                self._stop_process("send", cam_id, runtime_config)
                self._release_v4l2_device_owners(runtime_config, str(config.get("device", "/dev/video0")), cam_id)
                time.sleep(0.25)

        raise RuntimeError(
            f"Failed to start sender for camera {cam_id} after trying multiple source modes: "
            + " | ".join(errors)
        )

    def stop_sender(self, cam_id: str, config: dict):
        logger.info("Stopping sender %s", self._process_name("send", cam_id))
        self._stop_process("send", cam_id, config)

    def start_receiver(self, cam_id: str, config: dict):
        runtime_config = self._runtime_config("recv", config)
        self.stop_receiver(cam_id, config)
        port = config.get("target_port", 2140)

        pipeline = (
            f"gst-launch-1.0 -q udpsrc port={port} caps=\"application/x-rtp,media=video,payload=96,encoding-name=H264\" ! "
            "rtpjitterbuffer latency=0 drop-on-latency=true ! "
            "rtph264depay ! avdec_h264 ! videoconvert ! "
            "queue leaky=downstream max-size-buffers=1 max-size-bytes=0 max-size-time=0 ! "
            "autovideosink sync=false"
        )

        logger.info("Starting receiver window for %s on port %s", cam_id, port)
        self._launch_process("recv", cam_id, pipeline, runtime_config)
        if self._is_ssh_config(runtime_config):
            if not self._wait_for_process_state("recv", cam_id, runtime_config, True):
                raise self._start_failure_error("recv", cam_id, runtime_config)

    def stop_receiver(self, cam_id: str, config: dict):
        logger.info("Stopping receiver %s", self._process_name("recv", cam_id))
        self._stop_process("recv", cam_id, config)


camera_controller = CameraController()
