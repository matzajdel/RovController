#!/usr/bin/env python3
"""
OPS Control WebApp Backend Server — Main Application Entry Point
================================================================

This is the central FastAPI application that wires together every backend
module for the OPS Mars-rover control station.

Responsibilities (this file ONLY):
  • Create the FastAPI application instance
  • Configure CORS middleware
  • Register all route modules (routers)
  • Handle application startup / shutdown lifecycle (ROS 2 init)

All endpoint logic lives in dedicated route modules under ``routes/``.
Service singletons are created in ``services.py``.
Pydantic schemas shared across modules live in ``schemas.py``.
"""

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ROS 2 lifecycle helpers (init / shutdown / get_ros_node)
from services.ros_node import init_ros, shutdown_ros

# ---------------------------------------------------------------------------
# Route modules — each file handles a specific feature area
# ---------------------------------------------------------------------------
from routes import (
    health,         # GET /, /health, /status
    control,        # joystick, cmd_vel, stop, array_topic, LED on/off
    led,            # LED off / joystick, RGB colour control
    gamepad,        # gamepad list / select / stop, HID events, config, bridge
    steering,       # Sterowanie Nowe — drive mode, motor mode, speed limits
    bluetooth,      # Bluetooth scan, pair, mobile WiP
    vision,         # camera listing, streaming, configuration
    robot_view,     # URDF, joint states, IK, 3D visualisation
    screen_manager, # screen / script management for ROS 2 nodes
    topics,         # topic listing, dynamic publishing, saved commands
    ui_config,      # UI button configuration persistence
    science_layout, # Science Dashboard layout persistence
    science,        # science watcher CRUD + data retrieval
    ssh,            # SSH command execution on remote robot
    websocket,      # WebSocket real-time communication (/ws)
    gps,            # GPS waypoint / destination publishing
    satel,          # Satel RS-232 radio file encoder/decoder
    sequence,       # Science automation sequences
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="OPS Control WebApp Backend",
    description="Backend API server for OPS Control WebApp with ROS 2 integration",
    version="2.0.0",
)

# Allow the React frontend (any origin during development) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # In production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Lifecycle events
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Initialise the ROS 2 node and executor in a background thread."""
    logger.info("Starting OPS Control WebApp Backend...")
    init_ros()
    # Restore science watchers that were saved before last shutdown
    from services.ros_node import get_ros_node
    import asyncio
    await asyncio.sleep(1.0)  # Give ROS node a moment to fully initialise
    ros_node = get_ros_node()
    if ros_node:
        ros_node.load_science_xml()
        logger.info("Science watchers restored from disk")


@app.on_event("shutdown")
async def shutdown_event():
    """Gracefully shut down ROS 2 node and executor."""
    logger.info("Shutting down OPS Control WebApp Backend...")
    shutdown_ros()

# ---------------------------------------------------------------------------
# Router registration
# ---------------------------------------------------------------------------
# Basic informational endpoints (/, /health, /status)
app.include_router(health.router, tags=["health"])

# Robot control (joystick, velocity, stop, array buttons)
app.include_router(control.router, tags=["control"])

# LED & RGB colour control
app.include_router(led.router, tags=["led"])

# Gamepad management (list, select, stop, HID events, config, bridge)
app.include_router(gamepad.router, tags=["gamepad"])

# Sterowanie Nowe — advanced 4-mode steering
app.include_router(steering.router, tags=["steering"])

# Bluetooth device management
app.include_router(bluetooth.router, tags=["bluetooth"])

# Vision / camera system
app.include_router(vision.router, prefix="/vision", tags=["vision"])

# 3D robot visualisation & manipulator control
app.include_router(robot_view.router, prefix="/robot", tags=["robot_view"])

# ROS 2 screen & script management
app.include_router(screen_manager.router, tags=["screen_manager"])

# Dynamic ROS 2 topic publishing & saved commands
app.include_router(topics.router, tags=["topics"])

# UI button configuration persistence
app.include_router(ui_config.router, tags=["ui_config"])

# Science Dashboard layout persistence
app.include_router(science_layout.router, tags=["science_layout"])

# Science watcher management
app.include_router(science.router, tags=["science"])

# SSH remote command execution
app.include_router(ssh.router, tags=["ssh"])

# GPS waypoint / destination
app.include_router(gps.router, tags=["gps"])

# Satel RS-232 radio file encoder/decoder
app.include_router(satel.router, tags=["satel"])

# Science automation sequences
app.include_router(sequence.router, tags=["sequence"])

# WebSocket real-time channel
app.include_router(websocket.router, tags=["websocket"])

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    """
    Run the server directly.

    Configuration via environment variables:
      HOST      — listen address  (default 0.0.0.0)
      PORT      — listen port     (default 2137)
      LOG_LEVEL — uvicorn level   (default info)
    """
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "2137"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "info")

    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level=LOG_LEVEL,
    )
