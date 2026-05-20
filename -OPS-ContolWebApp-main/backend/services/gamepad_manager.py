"""
Gamepad discovery and event handling utilities.

This module provides functionality for:
- Detecting and listing connected HID gamepad devices
- Setting up event listeners for gamepad input
- Translating gamepad events (buttons, triggers, analog sticks) to ROS2 commands
- Managing gamepad lifecycle (activation, deactivation, cleanup)

The GamepadManager class handles device scanning and event loop management,
while create_gamepad_event_handler provides a factory for creating event handlers
that translate gamepad input into robot control commands.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import evdev
from evdev import ecodes

from services.ros_node import ROSNode

logger = logging.getLogger(__name__)

# Global speed multiplier for gamepad control (can be adjusted at runtime)
PAD_SPEED_MULTIPLIER = 1.0


class GamepadManager:
    """
    Manage the lifecycle of evdev gamepad listeners.
    
    This class handles:
    - Scanning for available gamepad devices
    - Activating a specific gamepad for input
    - Running a background thread to listen for events
    - Stopping the event listener when needed
    
    Only one gamepad can be active at a time.
    """

    def __init__(self) -> None:
        """
        Initialize the GamepadManager.
        
        Automatically scans for connected gamepads on initialization.
        """
        self.devices: list[evdev.InputDevice] = []
        self.active_index: Optional[int] = None
        self.listener_thread: Optional[threading.Thread] = None
        self.listener_active = False
        self.callback: Optional[Callable[[evdev.InputEvent], None]] = None
        self.scan_gamepads()

    def scan_gamepads(self) -> None:
        """
        Scan for connected gamepad devices.
        
        Updates the internal device list with all detected HID event devices.
        Filters out joystick (js) devices to focus on event-based input.
        """
        self.devices = [
            evdev.InputDevice(path)
            for path in evdev.list_devices()
            if "event" in path and "js" not in path
        ]

    def list_gamepads(self) -> list[str]:
        """
        Get a list of connected gamepad device names.
        
        Returns:
            List of formatted strings with device name and path
        """
        return [f"{device.name} ({device.path})" for device in self.devices]

    def set_active(self, idx: int, callback: Callable[[evdev.InputEvent], None]) -> None:
        """
        Activate a gamepad and start listening for events.
        
        Stops any existing listener, then starts a new background thread
        to process events from the selected gamepad.
        
        Args:
            idx: Index of the gamepad in the devices list
            callback: Function to call for each gamepad event
        """
        self.active_index = idx
        self.callback = callback
        
        # Stop existing listener if running
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_active = False
            self.listener_thread.join()
        
        # Start new listener
        self.listener_active = True
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()

    def _listen_loop(self) -> None:
        """
        Internal event loop for reading gamepad events.
        
        Runs in a background thread, reading events from the active device
        and invoking the callback for each relevant event (button presses,
        analog stick movements).
        """
        if self.active_index is None or self.active_index >= len(self.devices):
            return
        
        device = self.devices[self.active_index]
        for event in device.read_loop():
            if not self.listener_active:
                break
            # Only process absolute axis and key events
            if event.type in (ecodes.EV_ABS, ecodes.EV_KEY) and self.callback:
                self.callback(event)

    def stop(self) -> None:
        """
        Stop the active gamepad listener.
        
        Signals the listener thread to stop and waits for it to finish.
        """
        self.listener_active = False
        if self.listener_thread:
            self.listener_thread.join()


# Mapping of gamepad buttons to array topic indices and values
# Format: button_code -> (array_index, value)
# Used to translate button presses to specific array topic commands
BUTTON_TO_ARRAY = {
    ecodes.BTN_WEST: (1, 100),      # Y button -> index 1, value 100
    ecodes.BTN_EAST: (1, -100),     # B button -> index 1, value -100
    ecodes.BTN_NORTH: (2, 100),     # X button -> index 2, value 100
    ecodes.BTN_SOUTH: (2, -100),    # A button -> index 2, value -100
    ecodes.BTN_DPAD_UP: (3, 100),   # D-pad up -> index 3, value 100
    ecodes.BTN_DPAD_RIGHT: (4, -100),  # D-pad right -> index 4, value -100
    ecodes.BTN_DPAD_DOWN: (3, 100),    # D-pad down -> index 3, value 100
    ecodes.BTN_DPAD_LEFT: (4, -100),   # D-pad left -> index 4, value -100
    ecodes.BTN_THUMBL: (5, 100),    # Left stick press -> index 5, value 100
    ecodes.BTN_THUMBR: (5, -100),   # Right stick press -> index 5, value -100
}


def create_gamepad_event_handler(node_provider: Callable[[], Optional[ROSNode]]) -> Callable[[evdev.InputEvent], None]:
    """
    Create an event handler for translating gamepad input to robot commands.
    
    This factory function creates a stateful event handler that:
    - Tracks trigger and button states
    - Translates analog triggers to robot velocity commands (tank drive)
    - Maps button presses to array topic commands
    - Handles D-pad input for discrete array topic control
    
    The handler uses a tank drive model where left and right triggers control
    left and right wheel speeds respectively. Shoulder buttons (L1/R1) reverse
    the direction of their corresponding trigger.
    
    Args:
        node_provider: Function that returns the active ROS node (or None)
    
    Returns:
        Event handler function that processes gamepad events
    """

    # State tracking for analog triggers
    axis_values = {
        ecodes.ABS_Z: 0.0,      # Left trigger (Z-axis)
        ecodes.ABS_RZ: 0.0,     # Right trigger (RZ-axis)
        ecodes.ABS_GAS: 0.0,    # Alternative: Gas pedal
        ecodes.ABS_BRAKE: 0.0,  # Alternative: Brake pedal
    }
    
    # State tracking for shoulder buttons (used for reversing trigger direction)
    button_states = {ecodes.BTN_TL: 0, ecodes.BTN_TR: 0}

    def on_event(event: evdev.InputEvent) -> None:
        """
        Handle a single gamepad event.
        
        Args:
            event: evdev input event from the gamepad
        """
        ros_node = node_provider()
        if not ros_node:
            return
        
        # Handle analog axis events (triggers, sticks, D-pad on some controllers)
        if event.type == ecodes.EV_ABS:
            # Update trigger state
            if event.code in (ecodes.ABS_Z, ecodes.ABS_RZ, ecodes.ABS_GAS, ecodes.ABS_BRAKE):
                axis_values[event.code] = event.value
                logger.info(
                    "Trigger values: ABS_Z=%s, ABS_RZ=%s, GAS=%s, BRAKE=%s",
                    axis_values.get(ecodes.ABS_Z, 0.0),
                    axis_values.get(ecodes.ABS_RZ, 0.0),
                    axis_values.get(ecodes.ABS_GAS, 0.0),
                    axis_values.get(ecodes.ABS_BRAKE, 0.0),
                )
            
            # Handle D-pad as analog axis (some controllers use this mode)
            if event.code == ecodes.ABS_HAT0Y:
                # D-pad vertical: -1 = up, 1 = down
                value = -100 if event.value == 1 else 100 if event.value == -1 else 0
                ros_node.set_array_topic(3, float(value))
            elif event.code == ecodes.ABS_HAT0X:
                # D-pad horizontal: -1 = left, 1 = right
                value = 100 if event.value == 1 else -100 if event.value == -1 else 0
                ros_node.set_array_topic(4, float(value))
            
            # Calculate robot velocity from triggers (tank drive model)
            # Prefer GAS/BRAKE if available (some gamepads), otherwise use Z/RZ
            left_trigger = axis_values.get(ecodes.ABS_BRAKE)
            right_trigger = axis_values.get(ecodes.ABS_GAS)
            if left_trigger is not None and right_trigger is not None:
                # Normalize from 0-1023 range to 0.0-1.0
                left_trigger = left_trigger / 1023.0
                right_trigger = right_trigger / 1023.0
            else:
                # Normalize from 0-255 range to 0.0-1.0
                left_trigger = axis_values.get(ecodes.ABS_Z, 0.0) / 255.0
                right_trigger = axis_values.get(ecodes.ABS_RZ, 0.0) / 255.0
            
            # Apply reverse direction if shoulder buttons are pressed
            reverse_left = button_states.get(ecodes.BTN_TL, 0)
            reverse_right = button_states.get(ecodes.BTN_TR, 0)
            left = left_trigger * (-1 if reverse_left else 1)
            right = right_trigger * (-1 if reverse_right else 1)
            
            # Tank drive: linear velocity is average, angular is difference
            linear_x = (left + right) / 2.0 * PAD_SPEED_MULTIPLIER
            angular_z = (left - right) / 2.0 * PAD_SPEED_MULTIPLIER
            ros_node.publish_cmd_vel(linear_x, angular_z)
        
        # Handle button press/release events
        elif event.type == ecodes.EV_KEY:
            # Track shoulder button state for trigger direction reversal
            if event.code in (ecodes.BTN_TL, ecodes.BTN_TR):
                button_states[event.code] = event.value
            
            # Map button presses to array topic commands
            if event.code in BUTTON_TO_ARRAY:
                idx, val = BUTTON_TO_ARRAY[event.code]
                # value is 1 for press, 2 for hold, 0 for release
                value = val if event.value in (1, 2) else 0
                ros_node.set_array_topic(idx, float(value))

    return on_event

