"""
sequence_runner.py — Async sequence executor for Science Automation
===================================================================
Runs multi-step sequences in a background thread.

Step types
----------
- publish  : publish a value to a ROS topic
- wait     : poll a ROS topic until a condition is met (or timeout)
- delay    : sleep for N seconds
- loop     : jump back to an earlier step and repeat block N times

Conditions for 'wait' steps
-----------------------------
eq, neq, gt, gte, lt, lte, contains
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

 

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory store of active / recent runs
# ---------------------------------------------------------------------------

_runs: Dict[str, Dict[str, Any]] = {}
_runs_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

def _is_equal(a: Any, b: Any) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in b:
            if k not in a or not _is_equal(a[k], b[k]): return False
        return True
    if getattr(a, '__iter__', None) and getattr(b, '__iter__', None) and not isinstance(a, (str, dict)) and not isinstance(b, (str, dict)):
        a_list, b_list = list(a), list(b)
        if len(a_list) != len(b_list): return False
        return all(_is_equal(x, y) for x, y in zip(a_list, b_list))
    try:
        return abs(float(a) - float(b)) < 1e-5
    except (TypeError, ValueError):
        return str(a) == str(b)

def _check_condition(actual: Any, condition: str, expected: Any) -> bool:
    """Return True if ``actual`` satisfies ``condition`` against ``expected``."""
    try:
        if condition == "eq":
            return _is_equal(actual, expected)
        if condition == "neq":
            return not _is_equal(actual, expected)
        if condition == "gt":
            return float(actual) > float(expected)
        if condition == "gte":
            return float(actual) >= float(expected)
        if condition == "lt":
            return float(actual) < float(expected)
        if condition == "lte":
            return float(actual) <= float(expected)
        if condition == "contains":
            return str(expected) in str(actual)
    except (TypeError, ValueError):
        # Fallback to string comparison
        if condition == "eq":
            return _is_equal(actual, expected)
        if condition == "neq":
            return not _is_equal(actual, expected)
        if condition == "contains":
            return str(expected) in str(actual)
    return False

# ---------------------------------------------------------------------------
# Topic polling via ROS node
# ---------------------------------------------------------------------------

def _get_latest_topic_value(ros_node: Any, topic: str) -> Optional[Any]:
    """Read the latest value for a topic from the science watchers buffer."""
    watcher = ros_node.science_watchers.get(topic)
    if watcher and watcher.get("buffer"):
        return watcher["buffer"][-1].get("value")
    return None

def _ensure_watcher(ros_node: Any, topic: str) -> None:
    """Register a temporary science watcher so we can read topic values."""
    if topic not in ros_node.science_watchers:
        try:
            ros_node.add_science_watcher(topic, frequency_hz=10.0, max_points=5)
        except Exception as exc:
            logger.warning("Could not register watcher for %s: %s", topic, exc)

# ---------------------------------------------------------------------------
# Step executors
# ---------------------------------------------------------------------------

def _apply_op(current: Any, delta: Any, op: str) -> Any:
    """Recursively apply math operation (+ or -) between current and delta values."""
    if isinstance(current, dict) and isinstance(delta, dict):
        res = {}
        for k in current:
            res[k] = _apply_op(current[k], delta.get(k, 0), op)
        return res
    if getattr(current, '__iter__', None) and getattr(delta, '__iter__', None) and not isinstance(current, (str, dict)) and not isinstance(delta, (str, dict)):
        current_list = list(current)
        delta_list = list(delta)
        # Pad shorter list with 0s if necessary, though ideally they are same length
        l = max(len(current_list), len(delta_list))
        current_list += [0] * (l - len(current_list))
        delta_list += [0] * (l - len(delta_list))
        return [_apply_op(c, d, op) for c, d in zip(current_list, delta_list)]
    
    try:
        c, d = float(current), float(delta)
        return c + d if op == "+=" else c - d
    except (TypeError, ValueError):
        return current


def _run_publish(step: Dict, ros_node: Any, run: Dict) -> Optional[str]:
    """Execute a 'publish' step. Returns None on success, error string on failure."""
    topic = step.get("topic", "")
    value = step.get("value")
    op = step.get("operation", "=")
    
    if not topic:
        return "Missing topic in publish step"

    # If modifying, we need to read the current state first
    if op in ("+=", "-=", "!"):
        _ensure_watcher(ros_node, topic)
        deadline = time.time() + 2.0
        current_val = None
        while time.time() < deadline:
            current_val = _get_latest_topic_value(ros_node, topic)
            if current_val is not None:
                break
            time.sleep(0.1)

        if current_val is None:
            # Fallback if topic hasn't published anything recently.
            # We assume current value is 0 or equivalent structure of 'value'
            if isinstance(value, dict):
                current_val = _apply_op(value, value, "-=") # dirty trick to get zero'd dict
            elif isinstance(value, list) or isinstance(value, tuple):
                current_val = [0] * len(value)
            else:
                current_val = 0

        # If modifying, we need to read the current state first
    current_val = None
    if op in ("+=", "-=", "!"):
        _ensure_watcher(ros_node, topic)
        deadline = time.time() + 2.0
        while time.time() < deadline:
            current_val = _get_latest_topic_value(ros_node, topic)
            if current_val is not None:
                break
            time.sleep(0.1)

        if current_val is None:
            # Fallback if topic hasn't published anything recently.
            if isinstance(value, dict):
                current_val = _apply_op(value, value, "-=") # dirty trick to get zero'd dict
            elif isinstance(value, (list, tuple)):
                current_val = [0] * len(value)
            else:
                current_val = 0

    # Background settings
    run_in_background = bool(step.get("run_in_background", False))
    try: interval = float(step.get("interval_s", 0.0))
    except ValueError: interval = 0.0

    # Cancel previous background thread for this topic
    task_id = str(uuid.uuid4())
    with _runs_lock:
        if "bg_tasks" not in run:
            run["bg_tasks"] = {}
        run["bg_tasks"][topic] = task_id
    
    # We resolve type once
    try:
        import importlib
        from datetime import datetime as _dt

        topic_list = ros_node.get_topic_names_and_types()
        topic_type = None
        for tname, ttypes in topic_list:
            if tname == topic:
                topic_type = ttypes[0] if ttypes else None
                break

        if not topic_type:
            from std_msgs.msg import Float64, Int32, Float64MultiArray, String as StringMsg
            from geometry_msgs.msg import Twist as TwistMsg
            if isinstance(value, list) or op != "=" and isinstance(current_val, list):
                MsgClass, topic_type, msg_name = Float64MultiArray, "std_msgs/msg/Float64MultiArray", "Float64MultiArray"
            elif isinstance(value, dict) or op != "=" and isinstance(current_val, dict):
                MsgClass, topic_type, msg_name = TwistMsg, "geometry_msgs/msg/Twist", "Twist"
            elif isinstance(value, bool) or op == "!":
                from std_msgs.msg import Bool as BoolMsg
                MsgClass, topic_type, msg_name = BoolMsg, "std_msgs/msg/Bool", "Bool"
            elif isinstance(value, int):
                MsgClass, topic_type, msg_name = Int32, "std_msgs/msg/Int32", "Int32"
            else:
                MsgClass, topic_type, msg_name = Float64, "std_msgs/msg/Float64", "Float64"
        else:
            parts = topic_type.split("/")
            pkg, msg_name = parts[0], parts[2]
            mod = importlib.import_module(f"{pkg}.msg")
            MsgClass = getattr(mod, msg_name)

        def _publish_loop():
            nonlocal current_val
            while True:
                try:
                    with _runs_lock:
                        if run.get("stop_requested") or run.get("status") not in ("running", "pending"):
                            return
                        if run.get("bg_tasks", {}).get(topic) != task_id:
                            return # superseded by new publish step for this topic
                    
                    if op == "!":
                        current_val = not bool(current_val)
                        pub_value = current_val
                    elif op in ("+=", "-="):
                        current_val = _apply_op(current_val, value, op)
                        pub_value = current_val
                    else:
                        pub_value = value

                    msg = _build_msg(MsgClass, msg_name, pub_value)

                    if not hasattr(ros_node, "custom_publishers"):
                        ros_node.custom_publishers = {}
                    pub_key = f"{topic}_{topic_type}"
                    if pub_key not in ros_node.custom_publishers:
                        ros_node.custom_publishers[pub_key] = ros_node.create_publisher(
                            MsgClass, topic, 10
                        )
                    ros_node.custom_publishers[pub_key].publish(msg)

                    watcher = ros_node.science_watchers.get(topic)
                    if watcher and watcher.get("buffer") is not None:
                        watcher["buffer"].append({"timestamp": _dt.now().isoformat(), "value": pub_value})
                        max_pts = watcher.get("max_points", 50)
                        if len(watcher["buffer"]) > max_pts:
                            del watcher["buffer"][: len(watcher["buffer"]) - max_pts]

                    logger.info("[SEQ] Published %s → %s (bg=%s)", topic, pub_value, run_in_background)
                    
                    if interval > 0:
                        deadline = time.time() + interval
                        while time.time() < deadline:
                            with _runs_lock:
                                if run.get("stop_requested") or run.get("status") not in ("running", "pending"):
                                    return
                                if run.get("bg_tasks", {}).get(topic) != task_id:
                                    return
                            time.sleep(0.05)
                    else:
                        break
                except Exception as loop_exc:
                    logger.error("[SEQ] Exception in bg publish loop for %s: %s", topic, loop_exc)
                    break

        if run_in_background and interval > 0:
            t = threading.Thread(target=_publish_loop, daemon=True)
            t.start()
        else:
            _publish_loop()

        return None
    except Exception as exc:
        return f"Publish error: {exc}"


def _build_msg(MsgClass: Any, msg_name: str, value: Any) -> Any:
    """Construct a ROS message from a Python value."""
    msg = MsgClass()
    try:
        if msg_name in ("Float64", "Float32"):
            msg.data = float(value)
        elif msg_name in ("Int64", "Int32", "Int16", "Int8", "UInt64", "UInt32", "UInt16", "UInt8"):
            msg.data = int(value)
        elif msg_name == "Bool":
            msg.data = bool(value)
        elif msg_name == "String":
            msg.data = str(value)
        elif msg_name in ("Float64MultiArray", "Float32MultiArray"):
            if isinstance(value, (list, tuple)):
                msg.data = [float(v) for v in value]
            else:
                msg.data = [float(value)]
        elif msg_name in ("Int64MultiArray", "Int32MultiArray", "Int16MultiArray", "Int8MultiArray"):
            if isinstance(value, (list, tuple)):
                msg.data = [int(v) for v in value]
            else:
                msg.data = [int(value)]
        elif msg_name == "Twist":
            if isinstance(value, dict):
                lv = value.get("linear", {})
                av = value.get("angular", {})
                msg.linear.x = float(lv.get("x", 0))
                msg.linear.y = float(lv.get("y", 0))
                msg.linear.z = float(lv.get("z", 0))
                msg.angular.x = float(av.get("x", 0))
                msg.angular.y = float(av.get("y", 0))
                msg.angular.z = float(av.get("z", 0))
        else:
            if hasattr(msg, "data"):
                msg.data = value
    except Exception as exc:
        logger.error("[SEQ] Error building msg %s for value %r (type: %s): %s", msg_name, value, type(value), exc)
    return msg


def _run_wait(step: Dict, ros_node: Any, run: Dict) -> Optional[str]:
    """Execute a 'wait' step — poll topic until condition met or timeout."""
    topic = step.get("topic", "")
    condition = step.get("condition", "eq")
    expected = step.get("value")
    timeout_s = float(step.get("timeout_s", 30))

    _ensure_watcher(ros_node, topic)

    deadline = time.time() + timeout_s
    actual = None
    while time.time() < deadline:
        if run.get("stop_requested"):
            return "stopped"
        actual = _get_latest_topic_value(ros_node, topic)
        if actual is not None and _check_condition(actual, condition, expected):
            logger.info("[SEQ] Wait satisfied: %s %s %s (actual=%s)", topic, condition, expected, actual)
            return None
        time.sleep(0.1)

    return f"Timeout after {timeout_s}s waiting for {topic} {condition} {expected} (Last actual: {actual})"


def _run_delay(step: Dict, ros_node: Any, run: Dict) -> Optional[str]:
    """Execute a 'delay' step."""
    seconds = float(step.get("seconds", 1))
    deadline = time.time() + seconds
    while time.time() < deadline:
        if run.get("stop_requested"):
            return "stopped"
        time.sleep(0.05)
    return None


_STEP_RUNNERS = {
    "publish": _run_publish,
    "wait": _run_wait,
    "delay": _run_delay,
}


def _run_loop(step: Dict, step_index: int, run: Dict) -> tuple[Optional[str], Optional[int]]:
    """
    Execute a 'loop' step.

    Expected fields:
      - repeat (int): how many times to repeat the block
      - loop_to (int): 1-based step index to jump back to
            - infinite (bool, optional): if true, always jump back until run is stopped

    Returns (error, jump_to_index).
    """
    try:
        repeat = int(step.get("repeat", 1))
        loop_to = int(step.get("loop_to", 1))
    except (TypeError, ValueError):
        return "Loop fields 'repeat' and 'loop_to' must be integers", None

    infinite = bool(step.get("infinite", False))

    if repeat <= 0:
        return None, None

    jump_idx = loop_to - 1  # UI is 1-based
    if jump_idx < 0:
        return "Loop target must be >= 1", None
    if jump_idx >= step_index:
        return "Loop target must point to an earlier step", None

    if infinite:
        return None, jump_idx

    # Keep per-run loop counters by loop-step index
    loop_state = run.setdefault("loop_state", {})
    current_count = int(loop_state.get(str(step_index), 0))

    if current_count < repeat - 1:
        loop_state[str(step_index)] = current_count + 1
        return None, jump_idx

    # Loop completed; reset counter so re-running the sequence starts cleanly
    loop_state[str(step_index)] = 0
    return None, None

# ---------------------------------------------------------------------------
# Main sequence runner (runs in background thread)
# ---------------------------------------------------------------------------

def _execute_sequence(run_id: str, steps: List[Dict], ros_node: Any) -> None:
    with _runs_lock:
        run = _runs.get(run_id)
        if not run:
            return

    i = 0
    total_steps = len(steps)
    while i < total_steps:
        step = steps[i]
        with _runs_lock:
            if run.get("stop_requested"):
                run["status"] = "stopped"
                run["message"] = "Stopped by user"
                return
            run["current_step"] = i
            run["step_states"][i] = "running"

        step_type = step.get("type", "")
        if step_type == "loop":
            error, jump_to = _run_loop(step, i, run)
        else:
            runner = _STEP_RUNNERS.get(step_type)
            if not runner:
                with _runs_lock:
                    run["step_states"][i] = "error"
                    run["status"] = "error"
                    run["message"] = f"Unknown step type: {step_type}"
                return
            error = runner(step, ros_node, run)
            jump_to = None

        with _runs_lock:
            if error:
                run["step_states"][i] = "error"
                run["status"] = "error"
                run["message"] = error
                return
            run["step_states"][i] = "done"

        i = jump_to if jump_to is not None else i + 1

    with _runs_lock:
        run["status"] = "done"
        run["current_step"] = len(steps)
        run["message"] = "Sequence completed successfully"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_sequence(steps: List[Dict], ros_node: Any) -> str:
    """Start a sequence in a background thread and return a run_id."""
    run_id = str(uuid.uuid4())
    run = {
        "run_id": run_id,
        "status": "running",           # running | done | error | stopped
        "current_step": 0,
        "total_steps": len(steps),
        "step_states": ["pending"] * len(steps),
        "message": "",
        "stop_requested": False,
    }
    with _runs_lock:
        _runs[run_id] = run

    t = threading.Thread(target=_execute_sequence, args=(run_id, steps, ros_node), daemon=True)
    t.start()
    return run_id


def get_run_status(run_id: str) -> Optional[Dict]:
    with _runs_lock:
        run = _runs.get(run_id)
        return dict(run) if run else None


def stop_run(run_id: str) -> bool:
    with _runs_lock:
        run = _runs.get(run_id)
        if run and run["status"] == "running":
            run["stop_requested"] = True
            return True
    return False


def list_runs() -> List[Dict]:
    with _runs_lock:
        return [dict(r) for r in _runs.values()]
