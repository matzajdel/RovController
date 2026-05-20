"""
Service Registry — Singleton instances shared across the backend.
=================================================================

Creates one instance of each service class and exposes them for import
by route modules and other backend code.

Usage:
    from service_registry import gamepad_manager, screen_manager
"""
from __future__ import annotations

import os

from services.gamepad_manager import GamepadManager
from services.legacy_steering import LegacyControlService
from services.new_steering import NewControlService
from services.advanced_steering import SteeringNewService
from services.screen_manager import ScreenManager

BASE_DIR = os.path.dirname(__file__)

gamepad_manager = GamepadManager()
screen_manager = ScreenManager(base_dir=BASE_DIR)
legacy_control_service = LegacyControlService()
new_control_service = NewControlService()
steering_new_service = SteeringNewService()

__all__ = [
    "gamepad_manager",
    "screen_manager",
    "legacy_control_service",
    "new_control_service",
    "steering_new_service",
]
