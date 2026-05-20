"""
ROS 2 Topic Publishing & Management Endpoints
===============================================

Provides dynamic interaction with arbitrary ROS 2 topics:

  • Listing available topics and their types
  • Publishing messages to topics (auto-resolves message type, creates
    publishers on demand)
  • Saving / loading named "quick commands" for one-click publishing

This module does NOT handle:
  • UI button configuration  → see ``ui_config.py``
  • Science Dashboard layout → see ``science_layout.py``
  • Screen / script management → see ``ros2.py``

Known array topics (e.g. /array_topic, /ESP32_GIZ/led_state_topic) are
annotated with expected lengths and labels to assist the frontend.

Used by: Sterowanie tab, Science tab, and any panel that publishes to
arbitrary ROS 2 topics.
"""
from __future__ import annotations

 

import importlib
import json
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

from services.ros_node import get_ros_node

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent storage — saved commands
# ---------------------------------------------------------------------------
SAVED_COMMANDS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "saved_commands.json"
)

# Known array topic metadata for validation and frontend display
ARRAY_TOPIC_INFO = {
    "/ESP32_GIZ/led_state_topic": {
        "length": 3,
        "labels": ["Red", "Green", "Blue"],
    },
    "/array_topic": {
        "length": 6,
        "labels": ["Val 0", "Val 1", "Val 2", "Val 3", "Val 4", "Val 5"],
    },
    "/rgb": {
        "length": 3,
        "labels": ["Red", "Green", "Blue"],
    },
    "/arrow_keys": {
        "length": 2,
        "labels": ["X", "Y"],
    },
    "/gps_waypoint": {
        "length": 2,
        "labels": ["Lat", "Lon"],
    },
}


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def load_saved_commands() -> Dict[str, Any]:
    """Read saved commands from disk; return empty dict on error."""
    try:
        if os.path.exists(SAVED_COMMANDS_FILE):
            with open(SAVED_COMMANDS_FILE, "r") as f:
                return json.load(f)
        return {}
    except Exception as exc:
        logger.error("Error loading saved commands: %s", exc)
        return {}


def save_commands_to_file(commands: Dict[str, Any]) -> None:
    """Persist the commands dictionary to disk."""
    try:
        with open(SAVED_COMMANDS_FILE, "w") as f:
            json.dump(commands, f, indent=2)
    except Exception as exc:
        logger.error("Error saving commands: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Message construction helper
# ---------------------------------------------------------------------------

def _construct_message(MsgClass: Any, msg_name: str, value: Any) -> Any:
    """
    Dynamically build a ROS 2 message instance from its type name + value.

    Supported families:
      String, Int8–64, UInt8–64, Float32/64, Bool,
      Int/Float MultiArrays, Twist, and generic dict-based messages.
    """
    msg = None

    # String
    if msg_name == "String":
        from std_msgs.msg import String as StringMsg
        msg = StringMsg()
        msg.data = str(value)

    # Integer types
    elif msg_name in ["Int8", "Int16", "Int32", "Int64",
                      "UInt8", "UInt16", "UInt32", "UInt64"]:
        msg = MsgClass()
        msg.data = int(value)

    # Float types
    elif msg_name in ["Float32", "Float64"]:
        msg = MsgClass()
        msg.data = float(value)

    # Bool
    elif msg_name == "Bool":
        from std_msgs.msg import Bool as BoolMsg
        msg = BoolMsg()
        msg.data = (
            bool(value)
            if isinstance(value, bool)
            else (str(value).lower() in ["true", "1", "yes"])
        )

    # Integer MultiArray types
    elif msg_name in ["Int8MultiArray", "Int16MultiArray",
                      "Int32MultiArray", "Int64MultiArray"]:
        msg = MsgClass()
        if isinstance(value, str):
            value = json.loads(value)
        msg.data = [int(v) for v in value] if isinstance(value, list) else [int(value)]

    # Float MultiArray types
    elif msg_name in ["Float32MultiArray", "Float64MultiArray"]:
        msg = MsgClass()
        if isinstance(value, str):
            value = json.loads(value)
        msg.data = [float(v) for v in value] if isinstance(value, list) else [float(value)]

    # Twist (robot velocity commands — linear + angular)
    elif msg_name == "Twist":
        from geometry_msgs.msg import Twist as TwistMsg
        msg = TwistMsg()
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, dict):
            msg.linear.x = float(value.get("linear_x", 0.0))
            msg.linear.y = float(value.get("linear_y", 0.0))
            msg.linear.z = float(value.get("linear_z", 0.0))
            msg.angular.x = float(value.get("angular_x", 0.0))
            msg.angular.y = float(value.get("angular_y", 0.0))
            msg.angular.z = float(value.get("angular_z", 0.0))
        else:
            raise HTTPException(
                status_code=400,
                detail="Twist message requires dict with linear_x, angular_z, etc.",
            )

    # Generic fallback — try dict unpacking or .data assignment
    else:
        if isinstance(value, str):
            value = json.loads(value)
        if isinstance(value, dict):
            msg = MsgClass(**value)
        else:
            msg = MsgClass()
            if hasattr(msg, "data"):
                msg.data = value

    return msg


def _apply_multiarray_index_override(
    ros_node: Any,
    topic: str,
    msg_name: str,
    value: Any,
    array_index: Any,
    array_length: Any = None,
) -> Any:
    """
    Build full MultiArray payload when only a single index update is provided.

    Uses this precedence for the base array:
      1) current value if it's already a list
      2) cached HTTP publish state per topic
      3) last value from science watcher buffer
      4) empty list (zero-filled as needed)
    """
    if array_index is None or "MultiArray" not in msg_name:
        return value

    try:
        idx = int(array_index)
        if idx < 0:
            return value

        is_float = "Float" in msg_name
        cast = float if is_float else int

        if isinstance(value, list):
            current_array = list(value)
        else:
            cache = getattr(ros_node, "_http_multiarray_state", {})
            cached = cache.get(topic)
            if isinstance(cached, list):
                current_array = list(cached)
            else:
                watcher = getattr(ros_node, "science_watchers", {}).get(topic)
                if watcher and watcher.get("buffer"):
                    last_val = watcher["buffer"][-1].get("value")
                    current_array = list(last_val) if isinstance(last_val, (list, tuple)) else []
                else:
                    current_array = []

        requested_len = None
        if isinstance(array_length, int) and array_length > 0:
            requested_len = array_length
        elif isinstance(array_length, str):
            try:
                parsed = int(array_length)
                if parsed > 0:
                    requested_len = parsed
            except Exception:
                requested_len = None

        min_len = idx + 1
        if requested_len is not None:
            min_len = max(min_len, requested_len)

        if len(current_array) < min_len:
            current_array.extend([0] * (min_len - len(current_array)))

        current_array[idx] = cast(value)

        if not hasattr(ros_node, "_http_multiarray_state"):
            ros_node._http_multiarray_state = {}
        ros_node._http_multiarray_state[topic] = list(current_array)

        logger.info("MultiArray index override: %s at %d => %s", topic, idx, current_array)
        return current_array
    except Exception as exc:
        logger.warning("MultiArray index override failed for %s: %s", topic, exc)
        return value


# ---------------------------------------------------------------------------
# Endpoints — Topic listing
# ---------------------------------------------------------------------------

@router.get("/ros/topics")
async def get_ros_topics() -> Dict[str, Any]:
    """Get a flat list of all available ROS 2 topic names."""
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        topic_names_and_types = ros_node.get_topic_names_and_types()
        topics = [name for name, _ in topic_names_and_types]
        return {"topics": topics}
    except Exception as exc:
        logger.error("Error getting topics: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/ros2/topics")
def list_ros2_topics(name: str = None) -> Dict[str, Any]:
    """
    List ROS 2 topics with their message types.

    If *name* is provided, return just that single topic's info.
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        topic_list = ros_node.get_topic_names_and_types()
        topics = [
            {
                "name": tname,
                "type": ttypes[0] if ttypes else "unknown",
                "array_info": ARRAY_TOPIC_INFO.get(tname)
            }
            for tname, ttypes in topic_list
        ]

        if name:
            for t in topics:
                if t["name"] == name:
                    return {"name": t["name"], "type": t["type"]}
            raise HTTPException(status_code=404, detail="Topic not found")

        return {"topics": topics}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error listing ROS2 topics: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/ros2/topic_info")
def ros2_topic_info(name: str) -> Dict[str, Any]:
    """
    Get detailed information about a single topic (type + array metadata).
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        topic_list = ros_node.get_topic_names_and_types()
        for tname, ttypes in topic_list:
            if tname == name:
                info: Dict[str, Any] = {
                    "name": tname,
                    "type": ttypes[0] if ttypes else "unknown",
                }
                if tname in ARRAY_TOPIC_INFO:
                    info["array_length"] = ARRAY_TOPIC_INFO[tname]["length"]
                    info["labels"] = ARRAY_TOPIC_INFO[tname].get("labels", [])
                return info
        raise HTTPException(status_code=404, detail="Topic not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in /ros2/topic_info: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Science watcher intercept helper
# ---------------------------------------------------------------------------

import time as _time
from datetime import datetime as _datetime

def _feed_science_watcher(ros_node: Any, topic: str, value: Any) -> None:
    """
    Feed a published value directly into a science watcher buffer.
    Called whenever /ros/publish is used, so graph data works even for
    topics that are only published momentarily (e.g. sliders).
    """
    try:
        watcher = ros_node.science_watchers.get(topic)
        if not watcher:
            return

        freq = watcher.get("frequency_hz", 2.0)
        max_pts = watcher.get("max_points", 50)
        buffer = watcher.get("buffer")
        if buffer is None:
            return

        # Throttle inserts to match the configured frequency
        last_store = watcher.setdefault("_last_http_store", 0.0)
        now = _time.time()
        if now - last_store < (1.0 / freq):
            return
        watcher["_last_http_store"] = now

        buffer.append({"timestamp": _datetime.now().isoformat(), "value": value})
        if len(buffer) > max_pts:
            del buffer[: len(buffer) - max_pts]

        logger.debug("Science watcher HTTP intercept for %s: %s", topic, value)
    except Exception as exc:
        logger.warning("_feed_science_watcher error for %s: %s", topic, exc)


# ---------------------------------------------------------------------------
# Endpoints — Dynamic publishing
# ---------------------------------------------------------------------------

@router.post("/ros/publish")
async def publish_to_topic(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Publish a message to any ROS 2 topic.

    Body:
        topic (str) — topic name, e.g. "/cmd_vel"
        value (Any) — message content (type depends on topic)

    The message type is auto-resolved from the ROS 2 graph.
    Publishers are created on-demand and cached for reuse.
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")

    try:
        topic = body.get("topic")
        value = body.get("value")
        array_index = body.get("arrayIndex")
        array_length = body.get("arrayLength")
        if not topic:
            raise HTTPException(status_code=400, detail="Missing topic")

        # Resolve topic type from active ROS 2 graph
        topic_list = ros_node.get_topic_names_and_types()
        topic_type = None
        for tname, ttypes in topic_list:
            if tname == topic:
                topic_type = ttypes[0] if ttypes else None
                break

        # --- Fallback: infer type from value if topic not in ROS graph ---
        if not topic_type:
            from std_msgs.msg import Float64, String as StringMsg
            from std_msgs.msg import Float64MultiArray, Int32
            from geometry_msgs.msg import Twist as TwistMsg

            if isinstance(value, list):
                MsgClass = Float64MultiArray
                topic_type = "std_msgs/msg/Float64MultiArray"
                msg_name = "Float64MultiArray"
            elif isinstance(value, dict):
                MsgClass = TwistMsg
                topic_type = "geometry_msgs/msg/Twist"
                msg_name = "Twist"
            elif isinstance(value, bool):
                from std_msgs.msg import Bool as BoolMsg
                MsgClass = BoolMsg
                topic_type = "std_msgs/msg/Bool"
                msg_name = "Bool"
            elif isinstance(value, int):
                MsgClass = Int32
                topic_type = "std_msgs/msg/Int32"
                msg_name = "Int32"
            else:
                MsgClass = Float64
                topic_type = "std_msgs/msg/Float64"
                msg_name = "Float64"

            logger.info("Topic %s not in ROS — using fallback type %s", topic, topic_type)
            msg = _construct_message(MsgClass, msg_name, value)

            if not hasattr(ros_node, "custom_publishers"):
                ros_node.custom_publishers = {}
            pub_key = f"{topic}_{topic_type}"
            if pub_key not in ros_node.custom_publishers:
                ros_node.custom_publishers[pub_key] = ros_node.create_publisher(
                    MsgClass, topic, 10
                )
            ros_node.custom_publishers[pub_key].publish(msg)
            _feed_science_watcher(ros_node, topic, value)
            return {"status": "success", "topic": topic, "type": topic_type, "value": value, "fallback": True}

        # Parse type string, e.g. "std_msgs/msg/String" → ("std_msgs", "String")
        parts = topic_type.split("/")
        if len(parts) >= 3:
            pkg, msg_name = parts[0], parts[2]
        else:
            raise HTTPException(status_code=400, detail=f"Invalid topic type format: {topic_type}")

        # Dynamically import the message class
        try:
            mod = importlib.import_module(f"{pkg}.msg")
            MsgClass = getattr(mod, msg_name)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to import {pkg}.msg.{msg_name}: {exc}")

        value = _apply_multiarray_index_override(
            ros_node,
            topic,
            msg_name,
            value,
            array_index,
            array_length,
        )

        msg = _construct_message(MsgClass, msg_name, value)

        if not hasattr(ros_node, "custom_publishers"):
            ros_node.custom_publishers = {}
        pub_key = f"{topic}_{topic_type}"
        if pub_key not in ros_node.custom_publishers:
            ros_node.custom_publishers[pub_key] = ros_node.create_publisher(
                MsgClass, topic, 10
            )

        ros_node.custom_publishers[pub_key].publish(msg)
        if "MultiArray" in msg_name and isinstance(value, list):
            if not hasattr(ros_node, "_http_multiarray_state"):
                ros_node._http_multiarray_state = {}
            ros_node._http_multiarray_state[topic] = list(value)
        logger.info("Published to %s (type: %s): %s", topic, topic_type, value)
        _feed_science_watcher(ros_node, topic, value)
        return {"status": "success", "topic": topic, "type": topic_type, "value": value}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error publishing to topic: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Endpoints — Saved commands (quick-publish presets)
# ---------------------------------------------------------------------------

@router.get("/ros/saved_commands")
async def get_saved_commands() -> Dict[str, Any]:
    """Retrieve all saved commands grouped by topic."""
    try:
        commands = load_saved_commands()
        return {"commands": commands}
    except Exception as exc:
        logger.error("Error getting saved commands: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ros/saved_commands")
async def save_command(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Save a named command for one-click re-publishing.

    Body:
        topic     (str)  — topic name
        name      (str)  — unique command name
        value     (Any)  — message content
        type      (str)  — message type
        isDefault (bool) — auto-load on UI open (only one per topic)
        labels    (list) — optional per-index labels for array inputs
    """
    try:
        topic = body.get("topic")
        name = body.get("name")
        value = body.get("value")
        msg_type = body.get("type")

        if not topic or not name:
            raise HTTPException(status_code=400, detail="Missing topic or name")

        commands = load_saved_commands()

        if topic not in commands:
            commands[topic] = []

        # Remove existing with same name (update)
        commands[topic] = [c for c in commands[topic] if c.get("name") != name]

        # Enforce single default per topic
        is_default = body.get("isDefault", False)
        if is_default:
            for cmd in commands[topic]:
                cmd["isDefault"] = False

        commands[topic].append({
            "name": name,
            "value": value,
            "type": msg_type,
            "isDefault": is_default,
            "labels": body.get("labels", []),
        })

        save_commands_to_file(commands)
        logger.info("Saved command '%s' for topic '%s'", name, topic)
        return {"status": "success", "message": f"Command '{name}' saved"}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error saving command: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/ros/saved_commands")
async def delete_command(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Delete a saved command by topic + name.
    """
    try:
        topic = body.get("topic")
        name = body.get("name")

        if not topic or not name:
            raise HTTPException(status_code=400, detail="Missing topic or name")

        commands = load_saved_commands()

        if topic in commands:
            commands[topic] = [c for c in commands[topic] if c.get("name") != name]
            if not commands[topic]:
                del commands[topic]
            save_commands_to_file(commands)
            logger.info("Deleted command '%s' for topic '%s'", name, topic)
            return {"status": "success", "message": f"Command '{name}' deleted"}
        else:
            raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error deleting command: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Endpoints — Macros
# ---------------------------------------------------------------------------
import time
from fastapi import BackgroundTasks

def _execute_macro_sequence(steps: list[Dict[str, Any]]) -> None:
    ros_node = get_ros_node()
    if not ros_node:
        logger.error("Macro execution failed: ROS node not initialized")
        return

    logger.info("Starting macro execution with %d steps", len(steps))
    for i, step in enumerate(steps):
        action = step.get("action")
        logger.info("Executing Macro Step %d: %s", i + 1, action)

        try:
            if action == "publish":
                topic = step.get("topic")
                value = step.get("value")
                array_index = step.get("arrayIndex")
                array_length = step.get("arrayLength")
                
                if not topic:
                    logger.warning("Macro publish step missing topic")
                    continue

                topic_list = ros_node.get_topic_names_and_types()
                topic_type = None
                for tname, ttypes in topic_list:
                    if tname == topic:
                        topic_type = ttypes[0] if ttypes else None
                        break

                if not topic_type:
                    logger.warning("Macro publish failed, topic %s not found", topic)
                    continue

                parts = topic_type.split("/")
                if len(parts) >= 3:
                    pkg, msg_name = parts[0], parts[2]
                    mod = importlib.import_module(f"{pkg}.msg")
                    MsgClass = getattr(mod, msg_name)
                    
                    value = _apply_multiarray_index_override(
                        ros_node,
                        topic,
                        msg_name,
                        value,
                        array_index,
                        array_length,
                    )
                                
                    msg = _construct_message(MsgClass, msg_name, value)

                    if not hasattr(ros_node, "custom_publishers"):
                        ros_node.custom_publishers = {}

                    pub_key = f"{topic}_{topic_type}"
                    if pub_key not in ros_node.custom_publishers:
                        ros_node.custom_publishers[pub_key] = ros_node.create_publisher(
                            MsgClass, topic, 10
                        )

                    ros_node.custom_publishers[pub_key].publish(msg)
                    if "MultiArray" in msg_name and isinstance(value, list):
                        if not hasattr(ros_node, "_http_multiarray_state"):
                            ros_node._http_multiarray_state = {}
                        ros_node._http_multiarray_state[topic] = list(value)
                    logger.info("Macro published to %s: %s", topic, value)
                    
                    # Feed the watcher so it records this new broadcast too
                    from routes.topics import _feed_science_watcher
                    _feed_science_watcher(ros_node, topic, value)
                else:
                    logger.warning("Invalid topic type format %s", topic_type)

            elif action == "wait_time":
                delay = float(step.get("delay", 1.0))
                logger.info("Macro sleeping for %.1fs", delay)
                time.sleep(delay)

            elif action == "wait_topic":
                topic = step.get("topic")
                condition = step.get("condition", "==")
                expected_value = step.get("value")
                timeout = float(step.get("timeout", 30.0))
                
                if not topic or expected_value is None:
                    logger.warning("Macro wait_topic step missing topic or value")
                    continue
                    
                success = ros_node.wait_for_topic_sync(topic, expected_value, condition, timeout)
                if not success:
                    logger.warning("Macro step %d timed out waiting for %s %s %s. Aborting macro.", 
                                   i+1, topic, condition, expected_value)
                    break # Abort sequence on timeout

            else:
                logger.warning("Unknown macro action: %s", action)
                
        except Exception as e:
            logger.error("Error executing macro step %d (%s): %s", i + 1, action, e)
            break # Abort on error

    logger.info("Macro execution completed")


@router.post("/ros/macro")
async def execute_macro(background_tasks: BackgroundTasks, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Execute a macro sequence in the background.

    Body:
        steps (list) — array of step objects:
            - publish: { action: "publish", topic: "/cmd", value: "START" }
            - wait_time: { action: "wait_time", delay: 2.5 }
            - wait_topic: { action: "wait_topic", topic: "/status", condition: "==", value: "READY", timeout: 30.0 }
    """
    try:
        steps = body.get("steps", [])
        if not steps:
            raise HTTPException(status_code=400, detail="Macro must contain at least one step")

        background_tasks.add_task(_execute_macro_sequence, steps)
        return {"status": "macro_started", "steps_count": len(steps)}

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error starting macro: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
