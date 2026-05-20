"""
LED & RGB Strip Control Endpoints
==================================

Controls the robot's LED indicator and RGB light strip.

Endpoints:
  POST /led/off       — Turn the LED indicator off
  POST /led/joystick  — Set the LED to joystick-active state
  POST /set_rgb       — Set custom RGB colour values (R, G, B order)

The LED state is published as an Int32MultiArray to a ROS 2 topic.
RGB values are published as a Float32MultiArray to the /rgb topic.

Used by: Sterowanie tab (VirtualJoystick), Sterowanie Nowe (SteeringNewControl)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.ros_node import get_ros_node

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class RgbValues(BaseModel):
    """RGB colour values (0-255 each). Order: Red, Green, Blue."""
    r: int
    g: int
    b: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/led/off")
async def led_off() -> dict[str, object]:
    """Turn the LED indicator off (state [1, 0, 0])."""
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_led_state([1, 0, 0])
        return {"status": "success", "led_state": [1, 0, 0]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/led/joystick")
async def led_joystick() -> dict[str, object]:
    """Set the LED to joystick-active state (state [0, 1, 0])."""
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_led_state([0, 1, 0])
        return {"status": "success", "led_state": [0, 1, 0]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/set_rgb")
async def set_rgb(values: RgbValues) -> dict[str, object]:
    """
    Set custom RGB colour on the light strip.

    Accepts R, G, B values (0-255 each).

    Publishes a Float32MultiArray to /rgb topic.
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_rgb(float(values.r), float(values.g), float(values.b))
        return {"status": "success", "r": values.r, "g": values.g, "b": values.b}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
