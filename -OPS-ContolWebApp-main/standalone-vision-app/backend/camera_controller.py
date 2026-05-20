import logging
import shlex
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CameraController:
    """Manages GStreamer sender and receiver pipelines using named screen sessions."""

    def __init__(self):
        self.runtime_dir = Path(__file__).resolve().parent / ".runtime"
        self.runtime_dir.mkdir(exist_ok=True)
        self.remote_runtime_dir = "~/.vision_app_runtime"

    @staticmethod
    def _process_name(kind: str, cam_id: str) -> str:
        return f"cam_{kind}_{cam_id}"

    def _log_file(self, kind: str, cam_id: str) -> Path:
        return self.runtime_dir / f"{self._process_name(kind, cam_id)}.log"

    def _remote_log_file(self, kind: str, cam_id: str) -> str:
        return f"{self.remote_runtime_dir}/{self._process_name(kind, cam_id)}.log"

    @staticmethod
    def _is_ssh_config(config: dict) -> bool:
        return str(config.get("execution_mode", "local")).lower() == "ssh"

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
            "-p",
            str(config.get("ssh_port", 22)),
            self._ssh_target(config),
        ]

    def _screen_session_exists(self, kind: str, cam_id: str, config: dict) -> bool:
        session_name = self._process_name(kind, cam_id)
        if self._is_ssh_config(config):
            command = self._ssh_base_command(config) + [f"screen -ls | cat"]
        else:
            command = ["screen", "-ls"]

        result = subprocess.run(command, check=False, capture_output=True, text=True)
        output = f"{result.stdout}\n{result.stderr}"
        return session_name in output

    def _launch_process(self, kind: str, cam_id: str, pipeline: str, config: dict):
        session_name = self._process_name(kind, cam_id)
        if self._is_ssh_config(config):
            log_path = self._remote_log_file(kind, cam_id)
            remote_command = (
                f"mkdir -p {shlex.quote(self.remote_runtime_dir)} && "
                f"screen -L -Logfile {shlex.quote(log_path)} -DmS {shlex.quote(session_name)} "
                f"bash -lc {shlex.quote(pipeline)}"
            )
            command = self._ssh_base_command(config) + [remote_command]
        else:
            log_path = self._log_file(kind, cam_id)
            command = [
                "screen",
                "-L",
                "-Logfile",
                str(log_path),
                "-DmS",
                session_name,
                "bash",
                "-lc",
                pipeline,
            ]
        subprocess.run(command, check=False)

    def _stop_process(self, kind: str, cam_id: str, config: dict):
        session_name = self._process_name(kind, cam_id)
        if not self._screen_session_exists(kind, cam_id, config):
            logger.info("No %s process recorded for %s", kind, cam_id)
            return

        if self._is_ssh_config(config):
            command = self._ssh_base_command(config) + [f"screen -S {shlex.quote(session_name)} -X quit"]
        else:
            command = ["screen", "-S", session_name, "-X", "quit"]
        subprocess.run(command, check=False)

    def get_log_path(self, kind: str, cam_id: str, config: dict) -> str:
        if self._is_ssh_config(config):
            return f"{self._ssh_target(config)}:{self._remote_log_file(kind, cam_id)}"
        return str(self._log_file(kind, cam_id))

    def is_sender_running(self, cam_id: str, config: dict) -> bool:
        return self._screen_session_exists("send", cam_id, config)

    def is_receiver_running(self, cam_id: str, config: dict) -> bool:
        return self._screen_session_exists("recv", cam_id, config)

    def sync_statuses(self, camera_configs: dict) -> dict:
        for cam_id, config in camera_configs.items():
            config["sender_running"] = self.is_sender_running(cam_id, config)
            config["receiver_running"] = self.is_receiver_running(cam_id, config)
        return camera_configs

    def start_sender(self, cam_id: str, config: dict):
        """Constructs and runs the sender pipeline inside a screen session."""
        self.stop_sender(cam_id, config)
        
        device = config.get("device", "/dev/video0")
        width = config.get("width", 1280)
        height = config.get("height", 720)
        framerate = config.get("framerate", 24)
        bitrate = config.get("bitrate", 512)
        crop_top = config.get("crop_top", 0)
        crop_bottom = config.get("crop_bottom", 0)
        crop_left = config.get("crop_left", 0)
        crop_right = config.get("crop_right", 0)
        mirror_horizontal = config.get("mirror_horizontal", False)
        rotation = int(config.get("rotation", 0))
        encoder = str(config.get("encoder", "x264enc")).strip() or "x264enc"
        host = config.get("target_ip", "127.0.0.1")
        port = config.get("target_port", 2140)
        mirror_stage = "videoflip video-direction=horizontal-flip ! " if mirror_horizontal else ""

        rotation_stage = ""
        if rotation == 90:
            rotation_stage = "videoflip video-direction=90r ! "
        elif rotation == 180:
            rotation_stage = "videoflip video-direction=180 ! "
        elif rotation == 270:
            rotation_stage = "videoflip video-direction=90l ! "

        if encoder == "x264enc":
            encoder_stage = f"x264enc tune=zerolatency speed-preset=ultrafast bitrate={bitrate} ! "
        elif encoder == "openh264enc":
            encoder_stage = f"openh264enc bitrate={int(bitrate) * 1000} complexity=low ! h264parse ! "
        elif encoder == "avenc_h264":
            encoder_stage = f"avenc_h264 bitrate={int(bitrate) * 1000} ! h264parse ! "
        else:
            # Unknown value: keep the stream running with x264 defaults.
            encoder_stage = f"x264enc tune=zerolatency speed-preset=ultrafast bitrate={bitrate} ! "

        pipeline = (
            f"gst-launch-1.0 v4l2src device={device} ! "
            "videoconvert ! videoscale ! videorate ! "
            f"video/x-raw,width={width},height={height},framerate={framerate}/1 ! "
            f"{rotation_stage}{mirror_stage}"
            f"videocrop top={crop_top} bottom={crop_bottom} left={crop_left} right={crop_right} ! "
            f"{encoder_stage}"
            f"rtph264pay config-interval=1 pt=96 ! udpsink host={host} port={port}"
        )

        logger.info(f"Starting sender for {cam_id}: {pipeline}")
        self._launch_process("send", cam_id, pipeline, config)

    def stop_sender(self, cam_id: str, config: dict):
        """Stops the sender pipeline if it is running."""
        process_name = self._process_name("send", cam_id)
        logger.info(f"Stopping sender {process_name}")
        self._stop_process("send", cam_id, config)

    def start_receiver(self, cam_id: str, config: dict):
        """Runs the receiver pipeline in a screen session."""
        self.stop_receiver(cam_id, config)
        port = config.get("target_port", 2140)

        pipeline = (
            f"gst-launch-1.0 -q udpsrc port={port} caps=\"application/x-rtp,media=video,payload=96,encoding-name=H264\" ! "
            "rtpjitterbuffer latency=0 drop-on-latency=true ! "
            "rtph264depay ! avdec_h264 ! videoconvert ! "
            "queue leaky=downstream max-size-buffers=1 max-size-bytes=0 max-size-time=0 ! "
            f"autovideosink sync=false async=false"
        )

        logger.info(f"Starting receiver window for {cam_id} on port {port}")
        self._launch_process("recv", cam_id, pipeline, config)

    def stop_receiver(self, cam_id: str, config: dict):
        """Closes the receiver window by stopping its screen session."""
        process_name = self._process_name("recv", cam_id)
        logger.info(f"Stopping receiver {process_name}")
        self._stop_process("recv", cam_id, config)

camera_controller = CameraController()
