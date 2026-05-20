"""Legacy control service that emulates the provided ROS joystick behaviour."""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from services.ros_node import get_ros_node
from models import GamepadHidEvent

logger = logging.getLogger(__name__)

LEGACY_CONTROL_MODE = "bluetooth_mobile"
AXIS_EPSILON = 1e-3
TWIST_EPSILON = 1e-3
PADDLE_LIMIT = 4
MANIP_OUTPUT_COUNT = 6
MANIP_SENSITIVITY_DEFAULT = 100.0
MANIP_MIN_VALUE = -100.0
MANIP_MAX_VALUE = 100.0

MANIP_BUTTON_MAPPING: Dict[str, Tuple[int, int]] = {
    "A": (0, 1),
    "B": (0, -1),
    "X": (4, 1),
    "Y": (4, -1),
    "Back": (5, -1),
    "Start": (5, 1),
    "LJoyBut": (3, 1),
    "RJoyBut": (3, -1),
}

MANIP_DPAD_MAPPING: Dict[str, Tuple[int, int]] = {
    "DPadLeft": (2, 1),
    "DPadRight": (2, -1),
    "DPadDown": (1, 1),
    "DPadUp": (1, -1),
}

BUTTON_ORDER: List[str] = [
    "A",
    "B",
    "X",
    "Y",
    "LB",
    "RB",
    "Back",
    "Start",
    "LJoyBut",
    "RJoyBut",
    "DPadUp",
    "DPadDown",
    "DPadLeft",
    "DPadRight",
]


def _default_axes() -> Dict[str, float]:
    return {
        "left_x": 0.0,
        "left_y": 0.0,
        "right_x": 0.0,
        "right_y": 0.0,
        "lt": -1.0,
        "rt": -1.0,
    }


def _round(value: float, digits: int = 4) -> float:
    return float(f"{value:.{digits}f}")


def _clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _convert_trigger(value: float) -> float:
    """Convert trigger value [0, 1] into [-1, 1] range used by the legacy node."""
    return _clamp((value * 2.0) - 1.0)


def _almost_equal(sequence_a: Iterable[float], sequence_b: Iterable[float], epsilon: float) -> bool:
    for lhs, rhs in zip(sequence_a, sequence_b):
        if abs(lhs - rhs) > epsilon:
            return False
    return True


@dataclass
class ControllerState:
    """Mutable state for a single controller."""

    gamepad_id: Optional[str] = None
    axes: Dict[str, float] = field(default_factory=_default_axes)
    buttons: Dict[str, int] = field(default_factory=dict)
    paddle_buttons: List[int] = field(default_factory=lambda: [0] * PADDLE_LIMIT)
    # Maps (report_id, byte_index, bit_mask) -> paddle slot index
    paddle_mapping: Dict[Tuple[int, int, int], int] = field(default_factory=dict)
    last_reports: Dict[int, bytes] = field(default_factory=dict)
    last_axes_payload: Optional[List[float]] = None
    last_buttons_payload: Optional[List[int]] = None
    last_twist: Optional[Tuple[float, float]] = None
    manip_values: List[float] = field(default_factory=lambda: [0.0] * MANIP_OUTPUT_COUNT)
    manip_sensitivities: List[float] = field(
        default_factory=lambda: [MANIP_SENSITIVITY_DEFAULT] * MANIP_OUTPUT_COUNT
    )

    def allocate_paddle_slot(self) -> Optional[int]:
        occupied = set(self.paddle_mapping.values())
        for index in range(len(self.paddle_buttons)):
            if index not in occupied:
                return index
        return None


class LegacyControlService:
    """Process HID events and replicate the legacy ROS control scheme."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Controllers keyed by either gamepad index or HID identity string
        self._controllers: Dict[str, ControllerState] = {}
        self._active_key: Optional[str] = None
        self._speed_factor = 1.0
        self._max_linear_speed = 1.0
        self._max_angular_speed = 1.0

    def set_speed_factor(self, value: float) -> None:
        with self._lock:
            self._speed_factor = max(0.0, value)

    def set_active_controller(self, index: Optional[int], gamepad_id: Optional[str] = None) -> None:
        key = self._controller_key(index=index, gamepad_id=gamepad_id)
        with self._lock:
            if key not in self._controllers:
                self._controllers[key] = ControllerState(gamepad_id=gamepad_id)
            self._active_key = key
            logger.info("Legacy control active controller set to %s", key)

    def handle_hid_event(self, event: GamepadHidEvent) -> None:
        if event.control_mode and event.control_mode != LEGACY_CONTROL_MODE:
            return

        key = self._controller_key(
            index=event.gamepad_index,
            gamepad_id=event.gamepad_id,
            vendor_id=event.vendor_id,
            product_id=event.product_id,
        )
        with self._lock:
            state = self._controllers.setdefault(key, ControllerState(gamepad_id=event.gamepad_id))
            state.gamepad_id = event.gamepad_id or state.gamepad_id

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
            elif event.action == "report":
                changed = self._handle_report(state, event)

            if changed:
                self._publish_updates(state)

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
            x = _clamp(event.axes.get("x", 0.0))
            y = _clamp(event.axes.get("y", 0.0))
            if abs(state.axes["left_x"] - x) > AXIS_EPSILON or abs(state.axes["left_y"] - y) > AXIS_EPSILON:
                state.axes["left_x"] = _round(x)
                state.axes["left_y"] = _round(y)
                changed = True
        elif event.code == "RJoy" and event.axes:
            x = _clamp(event.axes.get("x", 0.0))
            y = _clamp(event.axes.get("y", 0.0))
            if abs(state.axes["right_x"] - x) > AXIS_EPSILON or abs(state.axes["right_y"] - y) > AXIS_EPSILON:
                state.axes["right_x"] = _round(x)
                state.axes["right_y"] = _round(y)
                changed = True
        elif event.code in {"LT", "RT"} and event.value is not None:
            axis_key = "lt" if event.code == "LT" else "rt"
            converted = _convert_trigger(event.value)
            if abs(state.axes[axis_key] - converted) > AXIS_EPSILON:
                state.axes[axis_key] = _round(converted)
                changed = True
        return changed

    def _handle_button(self, state: ControllerState, event: GamepadHidEvent) -> bool:
        pressed = 1 if event.action == "press" else 0
        previous = state.buttons.get(event.code)
        if previous == pressed:
            return False
        state.buttons[event.code] = pressed
        return True

    def _handle_state_snapshot(self, state: ControllerState, event: GamepadHidEvent) -> bool:
        pressed_codes = set(event.pressed_codes or [])
        changed = False
        dynamic_codes = list(state.buttons.keys()) + BUTTON_ORDER + list(pressed_codes)
        for code in set(dynamic_codes):
            current = 1 if code in pressed_codes else 0
            if state.buttons.get(code) != current:
                state.buttons[code] = current
                changed = True
        return changed

    def _handle_report(self, state: ControllerState, event: GamepadHidEvent) -> bool:
        if not event.report_hex:
            return False
        try:
            report_bytes = bytes.fromhex(event.report_hex)
        except ValueError:
            logger.debug("Invalid HID report payload: %s", event.report_hex)
            return False

        report_id = event.report_id or 0
        last_report = state.last_reports.get(report_id)
        state.last_reports[report_id] = report_bytes

        if last_report is None or len(last_report) != len(report_bytes):
            return False

        changed = False
        for index, (previous, current) in enumerate(zip(last_report, report_bytes)):
            diff = previous ^ current
            if diff == 0:
                continue
            for bit in range(8):
                mask = 1 << bit
                if not diff & mask:
                    continue
                bit_key = (report_id, index, mask)
                bit_value = 1 if current & mask else 0
                mapped_index = state.paddle_mapping.get(bit_key)
                if mapped_index is None and bit_value:
                    mapped_index = state.allocate_paddle_slot()
                    if mapped_index is not None:
                        # Learn which HID bit corresponds to which paddle on first press
                        state.paddle_mapping[bit_key] = mapped_index
                        logger.info(
                            "Discovered paddle mapping for key %s assigned to slot %d", bit_key, mapped_index
                        )
                if mapped_index is None or mapped_index >= len(state.paddle_buttons):
                    continue
                if state.paddle_buttons[mapped_index] != bit_value:
                    state.paddle_buttons[mapped_index] = bit_value
                    changed = True
        return changed

    def _update_manipulator_values(self, state: ControllerState) -> bool:
        new_values = [0.0] * MANIP_OUTPUT_COUNT

        for code, (index, direction) in MANIP_BUTTON_MAPPING.items():
            if state.buttons.get(code):
                new_values[index] += direction * state.manip_sensitivities[index]

        for code, (index, direction) in MANIP_DPAD_MAPPING.items():
            if state.buttons.get(code):
                new_values[index] += direction * state.manip_sensitivities[index]

        for idx, value in enumerate(new_values):
            new_values[idx] = max(MANIP_MIN_VALUE, min(MANIP_MAX_VALUE, value))

        if state.manip_values == new_values:
            return False

        state.manip_values = list(new_values)
        return True

    def _publish_updates(self, state: ControllerState) -> None:
        axes_payload = [
            state.axes["left_x"],
            state.axes["left_y"],
            state.axes["rt"],
            state.axes["right_x"],
            state.axes["right_y"],
            state.axes["lt"],
        ]
        buttons_payload = [state.buttons.get(code, 0) for code in BUTTON_ORDER]
        buttons_payload.extend(state.paddle_buttons)

        axes_changed = state.last_axes_payload is None or not _almost_equal(
            state.last_axes_payload, axes_payload, AXIS_EPSILON
        )
        buttons_changed = state.last_buttons_payload != buttons_payload
        manip_changed = self._update_manipulator_values(state)

        if not axes_changed and not buttons_changed and not manip_changed:
            return

        node = get_ros_node()
        if not node:
            logger.debug("ROS node unavailable; skipping legacy control publish")
            return

        if axes_changed or buttons_changed:
            state.last_axes_payload = list(axes_payload)
            state.last_buttons_payload = list(buttons_payload)
            node.publish_gamepad_state(axes_payload, buttons_payload)

            # LB (button index 4) reverses left, RB (button index 5) reverses right
            reverse_left = bool(len(buttons_payload) > 4 and buttons_payload[4])
            reverse_right = bool(len(buttons_payload) > 5 and buttons_payload[5])

            # LT is at axes_payload[5], RT is at axes_payload[2]
            left_trigger = (axes_payload[5] + 1.0) / 2.0
            right_trigger = (axes_payload[2] + 1.0) / 2.0

            if reverse_left:
                left_trigger = -left_trigger
            if reverse_right:
                right_trigger = -right_trigger

            linear = ((left_trigger + right_trigger) / 2.0) * self._max_linear_speed * self._speed_factor
            angular = ((left_trigger - right_trigger) / 2.0) * self._max_angular_speed * self._speed_factor

            twist = (_round(linear), _round(angular))
            if not (state.last_twist and _almost_equal(state.last_twist, twist, TWIST_EPSILON)):
                node.publish_cmd_vel(linear, angular)
                state.last_twist = twist
                logger.debug("Legacy control published cmd_vel linear=%.3f angular=%.3f", linear, angular)

        if manip_changed:
            node.publish_manipulator_values(state.manip_values)
            logger.debug("Legacy control published manipulator values: %s", state.manip_values)


