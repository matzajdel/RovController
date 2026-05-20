import logging
import json
from typing import Any

logger = logging.getLogger(__name__)

def parse_array(value: Any) -> list:
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        val_str = value.strip()
        if val_str.startswith("[") and val_str.endswith("]"):
            try:
                # Use json.loads with relaxed quotes replaced if necessary
                return json.loads(val_str.replace("'", '"'))
            except json.JSONDecodeError:
                return []
    return None

def check_topic_condition(current_value: Any, condition: str, expected_value: Any) -> bool:
    """Evaluate a condition against the current topic value and an expected value."""
    try:
        current_arr = parse_array(current_value)
        expected_arr = parse_array(expected_value)

        # If both are array-like, perform direct array comparison if supported
        if current_arr is not None and expected_arr is not None:
            if condition == "==":
                return current_arr == expected_arr
            elif condition == "!=":
                return current_arr != expected_arr
            else:
                logger.warning("Unsupported operator '%s' for array comparison. Falling back to ==", condition)
                return current_arr == expected_arr

        if current_arr is not None:
            # Fallback to checking just the first element if no list comparison possible
            current_value = current_arr[0] if current_arr else None
            
        # Attempt to cast expected_value to same type as current_value for comparison
        if type(current_value) is float:
            expected_value = float(expected_value)
        elif type(current_value) is int:
            expected_value = int(expected_value)
        elif type(current_value) is bool:
            if isinstance(expected_value, str):
                expected_value = expected_value.lower() in ("true", "1", "yes", "on")
            else:
                expected_value = bool(expected_value)
        else:
            expected_value = str(expected_value)
            current_value = str(current_value)

        if condition == "==":
            return current_value == expected_value
        elif condition == "!=":
            return current_value != expected_value
        elif condition == ">":
            return current_value > expected_value
        elif condition == ">=":
            return current_value >= expected_value
        elif condition == "<":
            return current_value < expected_value
        elif condition == "<=":
            return current_value <= expected_value
        else:
            logger.warning("Unknown condition operator: '%s'. Falling back to ==", condition)
            return current_value == expected_value

    except Exception as exc:
        logger.warning("Error evaluating condition: %s %s %s. E: %s", current_value, condition, expected_value, exc)
        return False
