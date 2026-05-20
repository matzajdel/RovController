"""
Sterowanie Nowe — Advanced 4-Mode Robot Steering Endpoints
==========================================================

Manages the "Sterowanie Nowe" (New Steering) control mode which provides
four distinct drive behaviours:

  PROSTY (0)    — Straight drive (linear X + linear Y)
  SKRĘT  (1)    — Turn drive (linear X + angular Z)
  OBRÓT  (2)    — Spin-in-place (angular Z only)
  FREESTYLE (3) — Arcade single-stick (linear X + angular Z from one stick)

Endpoints:
  POST /steering/set_drive_mode   — Switch between the 4 drive modes
  POST /steering/set_motor_mode   — Toggle PID (0.0) / PWM (1.0) control
  POST /steering/set_speed_limits — Set max linear speed and max turn rate
  GET  /steering/get_state        — Query current steering state

All state is managed by ``steering_new_service`` (SteeringNewService singleton).
The frontend counterpart is ``SteeringNewControl.jsx``.

Used by: Sterowanie tab → "Sterowanie Nowe" control mode
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException

from service_registry import steering_new_service

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/steering/set_drive_mode")
def set_steering_drive_mode(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Set the drive mode for steering_new control.

    Body:
        mode_id (int): 0=PROSTY, 1=SKRĘT, 2=OBRÓT, 3=FREESTYLE
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
            "drive_mode_name": state.get("drive_mode_name"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error setting drive mode: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/steering/set_motor_mode")
def set_steering_motor_mode(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Set the motor control mode.

    Body:
        motor_mode (float): 0.0 = PID/Standard, 1.0 = PWM direct
    """
    try:
        motor_mode = body.get("motor_mode")
        if motor_mode is None:
            raise HTTPException(status_code=400, detail="Missing 'motor_mode' parameter")

        steering_new_service.set_motor_mode(float(motor_mode))
        state = steering_new_service.get_current_state()

        return {"status": "success", "motor_mode": state.get("motor_mode")}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error setting motor mode: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/steering/set_speed_limits")
def set_steering_speed_limits(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Set maximum speed and turn rate.

    Body:
        max_speed (float): Maximum linear speed
        max_turn  (float): Maximum angular speed
    """
    try:
        max_speed = body.get("max_speed")
        max_turn = body.get("max_turn")

        if max_speed is None or max_turn is None:
            raise HTTPException(
                status_code=400,
                detail="Missing 'max_speed' or 'max_turn' parameter",
            )

        steering_new_service.set_speed_limits(float(max_speed), float(max_turn))
        state = steering_new_service.get_current_state()

        return {
            "status": "success",
            "max_speed": state.get("max_speed"),
            "max_turn": state.get("max_turn"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error setting speed limits: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/steering/get_state")
def get_steering_state() -> dict[str, Any]:
    """
    Get the current steering_new state.

    Returns drive mode, motor mode, speed/turn limits, manipulator state.
    """
    try:
        state = steering_new_service.get_current_state()
        return {"status": "success", "state": state}
    except Exception as exc:
        logger.error("Error getting steering state: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/steering/set_manipulator_sensitivities")
def set_manipulator_sensitivities(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Set manipulator sensitivities (6 DOF).

    Body:
        sensitivities (list[float]): Per-degree sensitivity [0..100] × 6
    """
    try:
        sensitivities = body.get("sensitivities")
        if sensitivities is None or not isinstance(sensitivities, list):
            raise HTTPException(
                status_code=400,
                detail="Missing or invalid 'sensitivities' parameter (expected list of 6 floats)",
            )

        steering_new_service.set_manipulator_sensitivities(sensitivities)
        state = steering_new_service.get_current_state()

        return {
            "status": "success",
            "manip_sensitivities": state.get("manip_sensitivities"),
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error setting manipulator sensitivities: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/steering/set_target_topic")
def set_target_topic(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """
    Set the ROS 2 topic used for velocity commands.

    Body:
        topic (str): The topic name (e.g. "cmd_vel", "cmd_vel_nav")
    """
    try:
        topic = body.get("topic")
        if not topic or not isinstance(topic, str):
            raise HTTPException(
                status_code=400,
                detail="Missing or invalid 'topic' parameter (expected non-empty string)",
            )

        actual_topic = steering_new_service.set_target_topic(topic.strip())
        return {"status": "success", "target_topic": actual_topic}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error setting target topic: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
