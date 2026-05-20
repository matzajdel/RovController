"""
Steering New Service - Advanced Robot Control
Based on SteeringTest with 4 drive modes: PROSTY, SKRET, OBROT, FREESTYLE
"""
from __future__ import annotations

import logging
import threading
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from services.ros_node import get_ros_node
from models import GamepadHidEvent, TwistFull

logger = logging.getLogger(__name__)

STEERING_NEW_MODE = "steering_new"
AXIS_EPSILON = 1e-3
TWIST_EPSILON = 1e-3
DEADZONE = 0.15

# --- Manipulator config (matches SteeringTest exactly) ---
MANIP_OUTPUT_COUNT = 6
MANIP_SENSITIVITY_DEFAULT = 100.0
MANIP_MIN_VALUE = -100.0
MANIP_MAX_VALUE = 100.0

# SteeringTest button_mapping:  button_index → (degree_index, direction)
# 0(A)→Podstawa+, 1(B)→Podstawa-, 2(X)→Chwytak obrót+, 3(Y)→Chwytak obrót-,
# 6(Back)→Chwytak zacisk-, 7(Start)→Chwytak zacisk+,
# 9(LJoyBut)→Nadgarstek+, 10(RJoyBut)→Nadgarstek-
MANIP_BUTTON_MAPPING: Dict[str, Tuple[int, int]] = {
    "A":       (0,  1),
    "B":       (0, -1),
    "X":       (4,  1),
    "Y":       (4, -1),
    "Back":    (5, -1),
    "Start":   (5,  1),
    "LJoyBut": (3,  1),
    "RJoyBut": (3, -1),
}

# SteeringTest HAT / D-pad mapping:
# Left→Ramię góra+, Right→Ramię góra-, Down→Ramię dół+, Up→Ramię dół-
MANIP_DPAD_MAPPING: Dict[str, Tuple[int, int]] = {
    "DPadLeft":  (2,  1),
    "DPadRight": (2, -1),
    "DPadDown":  (1,  1),
    "DPadUp":    (1, -1),
}


class DriveMode(Enum):
    """Drive modes matching SteeringTest implementation"""
    PROSTY = 0   # Jazda po krzyżu (X lub Y). Wymaga gazu (RT). RB odwraca.
    SKRET = 1    # Jazda po skosie (Mix X i Y). Wymaga gazu (RT). RB odwraca.
    OBROT = 2    # Tylko Angular Z. Wymaga gazu (RT). RB NIE DZIAŁA.
    FREESTYLE = 3  # Arcade (1 Gałka). RB NIE DZIAŁA.


@dataclass
class SteeringState:
    """State for a single controller in steering_new mode"""
    axes: Dict[str, float] = field(default_factory=lambda: {
        "left_x": 0.0,
        "left_y": 0.0,
        "right_x": 0.0,
        "right_y": 0.0,
        "lt": 1.0,
        "rt": 1.0,
    })
    buttons: Dict[str, int] = field(default_factory=dict)
    drive_mode: DriveMode = DriveMode.PROSTY
    reverse_mode: bool = False
    motor_mode: float = 1.0  # 0.0 = PWM, 1.0 = PID
    max_speed: float = 1.0
    max_turn: float = 1.0
    target_topic: str = "cmd_vel"  # Active ROS2 topic for velocity commands
    control_mode: Optional[str] = None
    last_twist: Optional[Tuple[float, float, float, float, float, float]] = None
    manip_values: list = field(default_factory=lambda: [0.0] * MANIP_OUTPUT_COUNT)
    manip_sensitivities: list = field(
        default_factory=lambda: [MANIP_SENSITIVITY_DEFAULT] * MANIP_OUTPUT_COUNT
    )
    last_manip_values: Optional[list] = None


class SteeringNewService:
    """Process HID events into advanced steering control with multiple drive modes"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._controllers: Dict[str, SteeringState] = {}
        self._active_key: Optional[str] = None

    def set_active_controller(self, index: Optional[int], gamepad_id: Optional[str] = None) -> None:
        key = self._controller_key(index=index, gamepad_id=gamepad_id)
        with self._lock:
            self._active_key = key
            self._controllers.setdefault(key, SteeringState())
            logger.info("Steering new active controller set to %s", key)

    def set_drive_mode(self, mode_id: int) -> None:
        """Set the drive mode for the active controller"""
        with self._lock:
            if self._active_key:
                state = self._controllers.get(self._active_key)
                if state:
                    try:
                        state.drive_mode = DriveMode(mode_id)
                        logger.info("Drive mode changed to: %s", state.drive_mode.name)
                        self._publish_twist(state)
                    except ValueError:
                        logger.error("Invalid drive mode id: %d", mode_id)
            else:
                logger.warning("No active controller to set drive mode")

    def set_motor_mode(self, motor_mode: float) -> None:
        """Set the motor control mode (0.0 = PID, 1.0 = PWM) for the active controller"""
        with self._lock:
            if self._active_key:
                state = self._controllers.get(self._active_key)
                if state:
                    state.motor_mode = motor_mode
                    mode_name = "PWM (1.0)" if motor_mode == 1.0 else "PID (0.0)"
                    logger.info("Motor mode changed to: %s", mode_name)
                    self._publish_twist(state)
            else:
                logger.warning("No active controller to set motor mode")

    def set_speed_limits(self, max_speed: float, max_turn: float) -> None:
        """Set the speed and turn limits for the active controller"""
        with self._lock:
            if self._active_key:
                state = self._controllers.get(self._active_key)
                if state:
                    state.max_speed = max_speed
                    state.max_turn = max_turn
                    logger.info("Speed limits updated: max_speed=%.2f, max_turn=%.2f", max_speed, max_turn)
                    self._publish_twist(state)
            else:
                logger.warning("No active controller to set speed limits")

    def set_manipulator_sensitivities(self, sensitivities: list) -> None:
        """Set manipulator sensitivities (list of 6 floats)"""
        with self._lock:
            if self._active_key:
                state = self._controllers.get(self._active_key)
                if state:
                    for i in range(min(len(sensitivities), MANIP_OUTPUT_COUNT)):
                        state.manip_sensitivities[i] = float(sensitivities[i])
                    logger.info("Manipulator sensitivities updated: %s", state.manip_sensitivities)

    def get_current_state(self) -> Dict[str, Any]:
        """Get the current state of the active controller"""
        with self._lock:
            if self._active_key:
                state = self._controllers.get(self._active_key)
                if state:
                    return {
                        "drive_mode": state.drive_mode.value,
                        "drive_mode_name": state.drive_mode.name,
                        "motor_mode": state.motor_mode,
                        "max_speed": state.max_speed,
                        "max_turn": state.max_turn,
                        "reverse_mode": state.reverse_mode,
                        "target_topic": state.target_topic,
                        "manip_sensitivities": list(state.manip_sensitivities),
                        "manip_values": list(state.manip_values),
                    }
            return {}

    def set_target_topic(self, topic: str) -> str:
        """Change the ROS2 topic for velocity commands."""
        node = get_ros_node()
        with self._lock:
            if self._active_key:
                state = self._controllers.get(self._active_key)
                if state:
                    state.target_topic = topic
            elif self._controllers:
                # Set on default controller
                key = next(iter(self._controllers))
                self._controllers[key].target_topic = topic
            else:
                # Create a default state
                self._controllers.setdefault("gamepad-0", SteeringState(target_topic=topic))
                if self._active_key is None:
                    self._active_key = "gamepad-0"

        # Actually switch the ROS publisher
        if node:
            actual = node.set_cmd_vel_topic(topic)
            logger.info("Target topic set to: %s", actual)
            return actual
        logger.warning("ROS node unavailable, topic queued: %s", topic)
        return topic

    def handle_hid_event(self, event: GamepadHidEvent) -> None:
        if event.control_mode and event.control_mode != STEERING_NEW_MODE:
            return

        key = self._controller_key(
            index=event.gamepad_index,
            gamepad_id=event.gamepad_id,
            vendor_id=event.vendor_id,
            product_id=event.product_id,
        )

        with self._lock:
            state = self._controllers.setdefault(key, SteeringState())
            state.control_mode = event.control_mode
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
                # Manipulator is now handled by frontend GAMEPAD_ARRAY_MAPPING
                # (Constants.js) → /array_topic/{id} endpoint directly.
                # self._update_and_publish_manipulator(state)
                self._publish_twist(state)
                # print(f"DEBUG STATE AFTER EVENT: axes={state.axes} buttons={state.buttons}", file=sys.stderr)

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

    def _handle_move(self, state: SteeringState, event: GamepadHidEvent) -> bool:
        changed = False
        if event.code == "LJoy" and event.axes:
            changed = self._update_axis(state.axes, "left_x", event.axes.get("x", 0.0)) or changed
            changed = self._update_axis(state.axes, "left_y", event.axes.get("y", 0.0)) or changed
        elif event.code == "RJoy" and event.axes:
            changed = self._update_axis(state.axes, "right_x", event.axes.get("x", 0.0)) or changed
            changed = self._update_axis(state.axes, "right_y", event.axes.get("y", 0.0)) or changed
        elif event.code in {"LT", "RT"} and event.value is not None:
            axis_key = "lt" if event.code == "LT" else "rt"
            # Convert browser 0..1 (released..pressed) to ROS convention 1..-1
            converted = 1.0 - (float(event.value) * 2.0)
            changed = self._update_axis(state.axes, axis_key, converted) or changed
        return changed

    @staticmethod
    def _update_axis(axes: Dict[str, float], key: str, value: float) -> bool:
        rounded = float(f"{value:.4f}")
        if abs(axes.get(key, 0.0) - rounded) <= AXIS_EPSILON:
            return False
        axes[key] = rounded
        return True

    def _handle_button(self, state: SteeringState, event: GamepadHidEvent) -> bool:
        pressed = 1 if event.action == "press" else 0
        previous = state.buttons.get(event.code, 0)
        state.buttons[event.code] = pressed

        # Also update trigger axis values on press/release so throttle
        # resets correctly when the trigger is released.
        if event.code in {"LT", "RT"} and event.value is not None:
            axis_key = "lt" if event.code == "LT" else "rt"
            converted = 1.0 - (float(event.value) * 2.0)
            self._update_axis(state.axes, axis_key, converted)

        if event.action == "press" and not previous:
            self._process_button_press(state, event.code)
            return True
        
        # RB button handling for reverse mode
        if event.code == "RB":
            if state.drive_mode in (DriveMode.PROSTY, DriveMode.SKRET):
                state.reverse_mode = (pressed == 1)
                return True
        
        if pressed != previous:
            return True
        return False

    def _handle_state_snapshot(self, state: SteeringState, event: GamepadHidEvent) -> bool:
        pressed_codes = set(event.pressed_codes or [])
        changed = False
        observed = set(state.buttons.keys()).union({"A", "B", "X", "Y", "RB", "LB"}).union(pressed_codes)
        
        for code in observed:
            current = 1 if code in pressed_codes else 0
            if state.buttons.get(code, 0) != current:
                state.buttons[code] = current
                changed = True
        return changed

    def _process_button_press(self, state: SteeringState, code: str) -> None:
        """Handle button presses — no mode switching (matches SteeringTest).
        Mode is changed only via GUI, buttons are reserved for manipulator."""
        pass

    # --- Manipulator (matches SteeringTest _joy_callback exactly) ---

    def _update_and_publish_manipulator(self, state: SteeringState) -> None:
        """Recalculate manipulator values from current button state and publish."""
        new_values = [0.0] * MANIP_OUTPUT_COUNT

        for code, (index, direction) in MANIP_BUTTON_MAPPING.items():
            if state.buttons.get(code):
                new_values[index] += direction * state.manip_sensitivities[index]

        for code, (index, direction) in MANIP_DPAD_MAPPING.items():
            if state.buttons.get(code):
                new_values[index] += direction * state.manip_sensitivities[index]

        # Clamp to [-100, 100]
        for i in range(MANIP_OUTPUT_COUNT):
            new_values[i] = max(MANIP_MIN_VALUE, min(MANIP_MAX_VALUE, new_values[i]))

        if state.last_manip_values == new_values:
            return

        state.manip_values = list(new_values)
        state.last_manip_values = list(new_values)

        node = get_ros_node()
        if node:
            node.publish_manipulator_values(new_values)
            logger.debug("Steering new published manipulator: %s", new_values)

    def _publish_twist(self, state: SteeringState) -> None:
        """Calculate and publish twist — exact port of SteeringTest._joy_callback."""
        node = get_ros_node()
        if not node:
            logger.debug("ROS node unavailable; skipping steering new publish")
            return

        # If control mode is STEERING_NEW, let the frontend handle twist publishing
        # to avoid conflicts and respect "throttle only in frontend" requirement.
        # Check safety buttons anyway if we want a global stop
        safety_stop = False
        # Happy buttons (708-711) often map to indices 16+ or specific codes
        for code, pressed in state.buttons.items():
            if pressed and (code.startswith("BTN_") and int(code.split("_")[1]) >= 16):
                safety_stop = True
                break
            if pressed and "Happy" in code:
                safety_stop = True
                break

        if state.control_mode == STEERING_NEW_MODE:
            # logger.debug("Skipping backend twist publish for %s mode", STEERING_NEW_MODE)
            return

        # Motor control mode on linear.z — always sent
        linear_z = state.motor_mode  # 0.0 = PID, 1.0 = PWM

        # RB reverse — matches SteeringTest lines 178-190
        dir_multiplier = -1.0 if state.reverse_mode else 1.0

        # --- Axis mapping ---
        # Browser Gamepad Y: UP = -1, DOWN = +1
        # SteeringTest (ROS joy): UP = +1, DOWN = -1
        # So we negate Y to match SteeringTest.
        right_x = self._apply_deadzone(state.axes.get("right_x", 0.0))
        right_y = self._apply_deadzone(state.axes.get("right_y", 0.0))

        # SteeringTest: val_trigger = axes[5] (RT), val_vert = axes[4], val_horz = axes[3]
        val_trigger = state.axes.get("rt", 1.0)
        val_vert = -right_y   # invert Y for ROS convention
        val_horz = right_x

        # --- Throttle (gas) — SteeringTest lines 197-199 ---
        throttle = (1.0 - val_trigger) / 2.0
        if throttle < 0.05:
            throttle = 0.0

        # --- Helper values — SteeringTest lines 201-206 ---
        abs_vert = abs(val_vert)
        abs_horz = abs(val_horz)
        deadzone = DEADZONE
        in_vertical = (abs_vert >= abs_horz) and (abs_vert > deadzone)
        in_horizontal = (abs_horz > abs_vert) and (abs_horz > deadzone)

        # --- Drive logic — SteeringTest lines 210-253 ---
        linear_x = 0.0
        linear_y = 0.0
        angular_z = 0.0

        if state.drive_mode == DriveMode.PROSTY:
            # SteeringTest lines 210-221
            if in_vertical or (throttle > 0.0 and not in_horizontal):
                direction = 1.0 if val_vert >= 0 else -1.0
                linear_x = throttle * state.max_speed * dir_multiplier * direction
                linear_y = 0.0
            elif in_horizontal:
                linear_x = 0.0
                linear_y = (throttle * state.max_speed) * dir_multiplier * (-1.0 if val_horz >= 0 else 1.0) + (-0.05 if val_horz >= 0 else 0.05)
            else:
                linear_x = 0.0
                linear_y = 0.0
            angular_z = 0.0

        elif state.drive_mode == DriveMode.SKRET:
            # SteeringTest lines 223-235
            skret_gain = 0.005
            if abs_vert > 0.1:
                linear_x = (val_vert * state.max_speed * skret_gain) * dir_multiplier * (throttle * 20 if throttle > 0.0 else 1)
            else:
                linear_x = 0.0
            if abs_horz > 0.1:
                linear_y = (-val_horz * state.max_speed * skret_gain) * dir_multiplier * (throttle * 20 if throttle > 0.0 else 1)
            else:
                linear_y = 0.0
            angular_z = 0.0


        elif state.drive_mode == DriveMode.OBROT:
            # SteeringTest lines 237-243
            linear_x = 0.0
            linear_y = 0.0
            if abs_horz > deadzone:
                angular_z = (val_horz * state.max_turn) * throttle * dir_multiplier + (-0.05 if val_horz >= 0 else 0.05)
            else:
                angular_z = 0.0

        elif state.drive_mode == DriveMode.FREESTYLE:
            # SteeringTest lines 245-249
            linear_x = val_vert * state.max_speed
            linear_y = 0.0
            p = 3  # "Do dopieszczenia"
            angular_z = math.copysign(abs(val_horz) ** p, val_horz) * state.max_turn

        # Force zero if safety stop active
        if safety_stop:
            linear_x = 0.0
            linear_y = 0.0
            angular_z = 0.0

        twist_tuple = (
            float(f"{linear_x:.3f}"),
            float(f"{linear_y:.3f}"),
            float(f"{linear_z:.3f}"),
            0.0,
            0.0,
            float(f"{angular_z:.3f}"),
        )

        #if state.last_twist and self._almost_equal(state.last_twist, twist_tuple):
        #    return

        state.last_twist = twist_tuple

        twist = TwistFull(
            linear_x=twist_tuple[0],
            linear_y=twist_tuple[1],
            linear_z=twist_tuple[2],
            angular_x=0.0,
            angular_y=0.0,
            angular_z=twist_tuple[5],
        )
        node.publish_twist_full(twist)
        logger.debug(
            "Steering new published twist: mode=%s linear=(%.3f, %.3f, %.3f) angular=(%.3f, %.3f, %.3f)",
            state.drive_mode.name,
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
    def _almost_equal(lhs: Tuple[float, ...], rhs: Tuple[float, ...]) -> bool:
        for left, right in zip(lhs, rhs):
            if abs(left - right) > TWIST_EPSILON:
                return False
        return True


steering_new_service = SteeringNewService()

__all__ = ["steering_new_service", "SteeringNewService"]
