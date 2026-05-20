"""Rover activity logger - logs cmd_vel and array_topic commands with file rotation."""
import logging
from logging.handlers import RotatingFileHandler
import os
from datetime import datetime

# Create logs directory if it doesn't exist
LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Log file path
ROVER_LOG_FILE = os.path.join(LOGS_DIR, "rover_activity.log")

# Create a dedicated logger for rover activity
rover_logger = logging.getLogger("rover_activity")
rover_logger.setLevel(logging.INFO)

# Create rotating file handler: 10MB max size, keep 5 backup files
# 10485760 bytes = 10MB
rotating_handler = RotatingFileHandler(
    ROVER_LOG_FILE,
    maxBytes=10485760,  # 10MB
    backupCount=5  # Keep 5 backup files
)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
rotating_handler.setFormatter(formatter)

# Add handler to logger
rover_logger.addHandler(rotating_handler)


def log_cmd_vel(linear_x: float, angular_z: float, source: str = "unknown"):
    """Log cmd_vel command."""
    rover_logger.info(
        f"CMD_VEL | linear_x={linear_x:.4f} | angular_z={angular_z:.4f} | source={source}"
    )


def log_array_topic(button_id: int, value: float, source: str = "unknown"):
    """Log array_topic command."""
    rover_logger.info(
        f"ARRAY_TOPIC | button_id={button_id} | value={value:.1f} | source={source}"
    )


def log_joystick(x: float, y: float, source: str = "unknown"):
    """Log joystick command."""
    rover_logger.info(
        f"JOYSTICK | x={x:.4f} | y={y:.4f} | source={source}"
    )


def log_twist(linear_x: float, linear_y: float, linear_z: float, 
              angular_x: float, angular_y: float, angular_z: float, source: str = "unknown"):
    """Log full twist command."""
    rover_logger.info(
        f"TWIST_FULL | lin_x={linear_x:.4f} | lin_y={linear_y:.4f} | lin_z={linear_z:.4f} | "
        f"ang_x={angular_x:.4f} | ang_y={angular_y:.4f} | ang_z={angular_z:.4f} | source={source}"
    )


def log_stop(source: str = "unknown"):
    """Log emergency stop."""
    rover_logger.warning(f"EMERGENCY_STOP | source={source}")


def log_gamepad_event(button: str, value: int, source: str = "unknown"):
    """Log gamepad button/axis event."""
    rover_logger.info(
        f"GAMEPAD | button={button} | value={value} | source={source}"
    )


def log_event(event_type: str, data: dict, source: str = "unknown"):
    """Log generic rover event."""
    data_str = " | ".join([f"{k}={v}" for k, v in data.items()])
    rover_logger.info(f"{event_type} | {data_str} | source={source}")
