"""Modern steering service inspired by the provided Tkinter/Pygame implementation."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

from services.ros_node import get_ros_node
from models import GamepadHidEvent, TwistFull

logger = logging.getLogger(__name__)

NEW_CONTROL_MODE = "bluetooth_jetson"
AXIS_EPSILON = 1e-3
TWIST_EPSILON = 1e-3
DEADZONE = 0.08

DEFAULT_MULTIPLIERS: Dict[str, Dict[str, float]] = {
    "TYPE_1": {"linear_x": 1.0, "linear_y": 1.0},
    "TYPE_2": {"linear_x": 1.0, "angular_z": 1.0},
    "TYPE_3": {"angular_z": 1.0},
}

BUTTON_CODES = {
    "A",
    "LB",
    "LJoyBut",
}


class SteeringMode(Enum):
    TYPE_1 = "TYPE_1"
    TYPE_2 = "TYPE_2"
    TYPE_3 = "TYPE_3"


@dataclass
class ControllerState:
    axes: Dict[str, float] = field(default_factory=lambda: {
        "left_x": 0.0,
        "left_y": 0.0,
        "right_x": 0.0,
        "right_y": 0.0,
        "lt": -1.0,
        "rt": -1.0,
    })
    buttons: Dict[str, int] = field(default_factory=dict)
    steering_mode: SteeringMode = SteeringMode.TYPE_1
    previous_mode: SteeringMode = SteeringMode.TYPE_1
    last_twist: Optional[Tuple[float, float, float, float, float, float]] = None


class NewControlService:
    """Process HID events into the "Sterowanie (nowe)" steering behaviour."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._controllers: Dict[str, ControllerState] = {}
        self._active_key: Optional[str] = None
        self._multipliers: Dict[str, Dict[str, float]] = {
            mode: dict(values) for mode, values in DEFAULT_MULTIPLIERS.items()
        }

    def set_active_controller(self, index: Optional[int], gamepad_id: Optional[str] = None) -> None:
        key = self._controller_key(index=index, gamepad_id=gamepad_id)
        with self._lock:
            self._active_key = key
            self._controllers.setdefault(key, ControllerState())
            logger.info("New control active controller set to %s", key)

    def handle_hid_event(self, event: GamepadHidEvent) -> None:
        if event.control_mode and event.control_mode != NEW_CONTROL_MODE:
            return

        key = self._controller_key(
            index=event.gamepad_index,
            gamepad_id=event.gamepad_id,
            vendor_id=event.vendor_id,
            product_id=event.product_id,
        )

        with self._lock:
            state = self._controllers.setdefault(key, ControllerState())
            if self._active_key is None:
                self._active_key = key
            if key != self._active_key:
                return

            changed = False

            if event.action == "move":
                changed = self._handle_move(state, event)
            elif event.action in {"press", "release"}:
                changed = self._handle_button(state, event)
            elif event.action == "state":
                changed = self._handle_state_snapshot(state, event)

            if changed:
                self._publish_twist(state)

    @staticmethod
    def _controller_key(
        *,
        index: Optional[int],
        gamepad_id: Optional[str],
        vendor_id: Optional[int] = None,
        product_id: Optional[int] = None,
    ) -> str:
        if index is not None:
            return f"gamepad-{index}"
        if gamepad_id:
            return f"hid-{gamepad_id}"
        if vendor_id is not None and product_id is not None:
            return f"hid-{vendor_id:04x}:{product_id:04x}"
        return "gamepad-0"

    def _handle_move(self, state: ControllerState, event: GamepadHidEvent) -> bool:
        changed = False
        if event.code == "LJoy" and event.axes:
            changed = self._update_axis(state.axes, "left_x", event.axes.get("x", 0.0)) or changed
            changed = self._update_axis(state.axes, "left_y", event.axes.get("y", 0.0)) or changed
        elif event.code == "RJoy" and event.axes:
            changed = self._update_axis(state.axes, "right_x", event.axes.get("x", 0.0)) or changed
            changed = self._update_axis(state.axes, "right_y", event.axes.get("y", 0.0)) or changed
        elif event.code in {"LT", "RT"} and event.value is not None:
            axis_key = "lt" if event.code == "LT" else "rt"
            converted = (float(event.value) * 2.0) - 1.0
            changed = self._update_axis(state.axes, axis_key, converted) or changed
        return changed

    @staticmethod
    def _update_axis(axes: Dict[str, float], key: str, value: float) -> bool:
        rounded = float(f"{value:.4f}")
        if abs(axes.get(key, 0.0) - rounded) <= AXIS_EPSILON:
            return False
        axes[key] = rounded
        return True

    def _handle_button(self, state: ControllerState, event: GamepadHidEvent) -> bool:
        pressed = 1 if event.action == "press" else 0
        previous = state.buttons.get(event.code, 0)
        state.buttons[event.code] = pressed
        if event.action == "press" and not previous:
            self._process_button_press(state, event.code)
            return True
        if pressed != previous:
            return True
        return False

    def _handle_state_snapshot(self, state: ControllerState, event: GamepadHidEvent) -> bool:
        pressed_codes = set(event.pressed_codes or [])
        changed = False
        observed = set(state.buttons.keys()).union(BUTTON_CODES).union(pressed_codes)
        for code in observed:
            current = 1 if code in pressed_codes else 0
            if state.buttons.get(code, 0) != current:
                state.buttons[code] = current
                changed = True
        return changed

    def _process_button_press(self, state: ControllerState, code: str) -> None:
        if code == "A":
            if state.steering_mode == SteeringMode.TYPE_1:
                state.steering_mode = SteeringMode.TYPE_2
            elif state.steering_mode == SteeringMode.TYPE_2:
                state.steering_mode = SteeringMode.TYPE_1
        elif code == "LJoyBut":
            if state.steering_mode == SteeringMode.TYPE_3:
                state.steering_mode = state.previous_mode
            else:
                state.previous_mode = state.steering_mode
                state.steering_mode = SteeringMode.TYPE_3
        logger.debug("New control mode for controller set to %s", state.steering_mode.value)

    def _publish_twist(self, state: ControllerState) -> None:
        node = get_ros_node()
        if not node:
            logger.debug("ROS node unavailable; skipping new control publish")
            return

        horizontal = self._apply_deadzone(state.axes.get("left_x", 0.0))
        vertical = self._apply_deadzone(state.axes.get("left_y", 0.0))
        trigger_value = self._convert_trigger(state.axes.get("lt", -1.0))
        bumper_pressed = bool(state.buttons.get("LB", 0))

        throttle = -trigger_value if bumper_pressed else trigger_value
        lateral = horizontal

        linear_x = 0.0
        linear_y = 0.0
        linear_z = 0.0
        angular_x = 0.0
        angular_y = 0.0
        angular_z = 0.0

        mode_key = state.steering_mode.value
        multipliers = self._multipliers.get(mode_key, {})

        if state.steering_mode == SteeringMode.TYPE_1:
            linear_x = throttle * multipliers.get("linear_x", 1.0)
            linear_y = -lateral * multipliers.get("linear_y", 1.0)
            linear_z = -vertical
        elif state.steering_mode == SteeringMode.TYPE_2:
            linear_x = throttle * multipliers.get("linear_x", 1.0)
            angular_z = -lateral * multipliers.get("angular_z", 1.0)
            linear_z = -vertical
        else:
            angular_z = lateral * multipliers.get("angular_z", 1.0)
            linear_z = -vertical

        twist_tuple = (
            float(f"{linear_x:.3f}"),
            float(f"{linear_y:.3f}"),
            float(f"{linear_z:.3f}"),
            float(f"{angular_x:.3f}"),
            float(f"{angular_y:.3f}"),
            float(f"{angular_z:.3f}"),
        )

        if state.last_twist and self._almost_equal(state.last_twist, twist_tuple):
            return

        state.last_twist = twist_tuple

        twist = TwistFull(
            linear_x=twist_tuple[0],
            linear_y=twist_tuple[1],
            linear_z=twist_tuple[2],
            angular_x=twist_tuple[3],
            angular_y=twist_tuple[4],
            angular_z=twist_tuple[5],
        )
        node.publish_twist_full(twist)
        logger.debug(
            "New control published twist: mode=%s linear=(%.3f, %.3f, %.3f) angular=(%.3f, %.3f, %.3f)",
            state.steering_mode.value,
            twist.linear_x,
            twist.linear_y,
            twist.linear_z,
            twist.angular_x,
            twist.angular_y,
            twist.angular_z,
        )

    @staticmethod
    def _apply_deadzone(value: float) -> float:
        if abs(value) < DEADZONE:
            return 0.0
        return float(value)

    @staticmethod
    def _convert_trigger(raw: float) -> float:
        return max(0.0, min(1.0, (raw + 1.0) / 2.0))

    @staticmethod
    def _almost_equal(lhs: Iterable[float], rhs: Iterable[float]) -> bool:
        for left, right in zip(lhs, rhs):
            if abs(left - right) > TWIST_EPSILON:
                return False
        return True


new_control_service = NewControlService()

__all__ = ["new_control_service", "NewControlService"]
