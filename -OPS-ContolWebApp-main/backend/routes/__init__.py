"""
Route module exports for the backend application.
===================================================

Each module handles a specific feature area of the OPS Control WebApp.
Import them here so main.py can register all routers in one place.
"""
from . import (
    health,          # GET /, /health, /status
    control,         # joystick, cmd_vel, stop, array_topic
    led,             # LED off/joystick, RGB colour
    gamepad,         # gamepad list/select/stop, HID events, config, bridge
    steering,        # Sterowanie Nowe drive/motor modes, speed limits
    bluetooth,       # Bluetooth scan, pair, mobile WiP
    vision,          # camera listing, streaming, configuration
    robot_view,      # URDF, joint states, IK, 3D vis
    screen_manager,  # screen / script management
    topics,          # topic listing, dynamic publishing, saved commands
    ui_config,       # UI button config persistence
    science_layout,  # Science Dashboard layout persistence
    science,         # science watcher CRUD + data
    ssh,             # SSH remote command execution
    websocket,       # WebSocket real-time channel
    gps,             # GPS waypoint / destination
)

__all__ = [
    "health",
    "control",
    "led",
    "gamepad",
    "steering",
    "bluetooth",
    "vision",
    "robot_view",
    "screen_manager",
    "topics",
    "ui_config",
    "science_layout",
    "science",
    "ssh",
    "websocket",
    "gps",
]
