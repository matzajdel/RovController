"""Pydantic schemas shared across the backend."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Literal

from pydantic import BaseModel


class JoystickCommand(BaseModel):
    """Joystick command data model."""

    x: float
    y: float
    timestamp: Optional[str] = None


class RobotStatus(BaseModel):
    """Robot status data model."""

    connected: bool
    last_command: Optional[Dict[str, Any]] = None
    last_update: str


class TwistFull(BaseModel):
    """Full Twist command with all components."""

    linear_x: float = 0.0
    linear_y: float = 0.0
    linear_z: float = 0.0
    angular_x: float = 0.0
    angular_y: float = 0.0
    angular_z: float = 0.0


class GamepadSelect(BaseModel):
    """Payload used to select an active gamepad."""

    index: int


class GamepadHidEvent(BaseModel):
    """Frontend HID event payload forwarded to the backend."""

    code: str
    action: Literal["press", "release", "move", "state", "report"]
    value: Optional[float] = None
    axes: Optional[Dict[str, float]] = None
    control_mode: Optional[str] = None
    raw_index: Optional[int] = None
    gamepad_index: Optional[int] = None
    gamepad_id: Optional[str] = None
    pressed_codes: Optional[List[str]] = None
    report_id: Optional[int] = None
    report_hex: Optional[str] = None
    vendor_id: Optional[int] = None
    product_id: Optional[int] = None
    usage_page: Optional[int] = None
    usage: Optional[int] = None
    timestamp: Optional[str] = None


class BluetoothPairRequest(BaseModel):
    """Request body used to pair a bluetooth device."""

    mac: str


class ScriptPayload(BaseModel):
    """Definition of a ROS 2 screen script entry."""

    name: str
    command: str
    session: Optional[str] = None
    working_dir: Optional[str] = None
    auto_restart: bool = False
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class ScreenRunRequest(BaseModel):
    """Parameters accepted when launching a screen session."""

    script_name: Optional[str] = None
    session: Optional[str] = None
    command: Optional[str] = None
    working_dir: Optional[str] = None
    auto_restart: Optional[bool] = None


class ScreenKillRequest(BaseModel):
    """Parameters accepted when terminating a screen session."""

    session: str


class ScienceWatcherRequest(BaseModel):
    """Definition of a science topic watcher."""

    topic: str
    frequency_hz: float
    max_points: int


class SSHCommandRequest(BaseModel):
    """SSH command execution request for remote robot."""

    host: str = "192.168.2.50"
    user: str = "lrt_geeokom"
    password: Optional[str] = 'qwerty'
    command: str
    session_name: Optional[str] = None  # For tracking in frontend


class MicroRosDeviceRequest(BaseModel):
    """MicroROS agent action request keyed by stable STM32 USB device ID."""

    device_id: str
    baud_rate: int = 115200

