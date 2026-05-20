"""Gamepad management endpoints."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Body

from services.gamepad_manager import create_gamepad_event_handler
from services.ros_node import get_ros_node
from models import GamepadHidEvent, GamepadSelect
from service_registry import gamepad_manager, legacy_control_service, new_control_service, steering_new_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/gamepads")
def list_gamepads() -> dict[str, object]:
    gamepad_manager.scan_gamepads()
    return {"gamepads": gamepad_manager.list_gamepads()}


@router.post("/gamepads/select")
def select_gamepad(sel: GamepadSelect) -> dict[str, object]:
    callback = create_gamepad_event_handler(get_ros_node)
    gamepad_manager.set_active(sel.index, callback)
    legacy_control_service.set_active_controller(sel.index)
    new_control_service.set_active_controller(sel.index)
    steering_new_service.set_active_controller(sel.index)
    return {"status": "selected", "index": sel.index}


@router.post("/gamepads/stop")
def stop_gamepad() -> dict[str, str]:
    gamepad_manager.stop()
    return {"status": "stopped"}


@router.post("/gamepads/hid-event")
def record_gamepad_hid_event(event: GamepadHidEvent) -> dict[str, object]:
    payload = event.dict(exclude_none=True)
    logger.info("Received HID event: %s", payload)
    legacy_control_service.handle_hid_event(event)
    steering_new_service.handle_hid_event(event)
    new_control_service.handle_hid_event(event)
    return {"status": "received", "received_at": datetime.now().isoformat(), "event": payload}


@router.post("/steering/set_drive_mode")
def set_steering_drive_mode(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Set the drive mode for steering_new control.

    Request body:
        - mode_id: int - Drive mode ID (0=PROSTY, 1=SKRET, 2=OBROT, 3=FREESTYLE)

    Returns:
        Status dict with current drive mode
    """
    try:
        mode_id = body.get("mode_id")
        if mode_id is None:
            raise HTTPException(status_code=400, detail="Missing 'mode_id' parameter")

        steering_new_service.set_drive_mode(int(mode_id))
        state = steering_new_service.get_current_state()

        return {
            "status": "success",
            "drive_mode": state.get("drive_mode"),
            "drive_mode_name": state.get("drive_mode_name")
        }
    except Exception as exc:
        logger.error("Error setting drive mode: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/steering/set_motor_mode")
def set_steering_motor_mode(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Set the motor control mode for steering_new control.

    Request body:
        - motor_mode: float - Motor mode (0.0 = PID/Standard, 1.0 = PWM)

    Returns:
        Status dict with current motor mode
    """
    try:
        motor_mode = body.get("motor_mode")
        if motor_mode is None:
            raise HTTPException(status_code=400, detail="Missing 'motor_mode' parameter")

        steering_new_service.set_motor_mode(float(motor_mode))
        state = steering_new_service.get_current_state()

        return {
            "status": "success",
            "motor_mode": state.get("motor_mode")
        }
    except Exception as exc:
        logger.error("Error setting motor mode: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/steering/set_speed_limits")
def set_steering_speed_limits(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Set the speed and turn limits for steering_new control.

    Request body:
        - max_speed: float - Maximum linear speed
        - max_turn: float - Maximum angular speed

    Returns:
        Status dict with current limits
    """
    try:
        max_speed = body.get("max_speed")
        max_turn = body.get("max_turn")

        if max_speed is None or max_turn is None:
            raise HTTPException(status_code=400, detail="Missing 'max_speed' or 'max_turn' parameter")

        steering_new_service.set_speed_limits(float(max_speed), float(max_turn))
        state = steering_new_service.get_current_state()

        return {
            "status": "success",
            "max_speed": state.get("max_speed"),
            "max_turn": state.get("max_turn")
        }
    except Exception as exc:
        logger.error("Error setting speed limits: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/steering/get_state")
def get_steering_state() -> dict[str, Any]:
    """
    Get the current state of steering_new control.

    Returns:
        Current state including drive mode, motor mode, and speed limits
    """
    try:
        state = steering_new_service.get_current_state()
        return {
            "status": "success",
            "state": state
        }
    except Exception as exc:
        logger.error("Error getting steering state: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

