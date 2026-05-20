"""
ROS2 topic publishing and management endpoints.

This module provides endpoints for:
- Listing available ROS2 topics
- Publishing messages to arbitrary topics dynamically
- Managing saved commands for quick topic publishing
- Getting detailed topic information
"""
from __future__ import annotations

import importlib
import json
import logging
import os
from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException

from ros_interface import get_ros_node

router = APIRouter()
logger = logging.getLogger(__name__)

# File path for persisting saved commands
# Use absolute path to be safe, or relative to this file
SAVED_COMMANDS_FILE = os.path.join(os.path.dirname(__file__), "..", "saved_commands.json")

# Known array topic lengths and labels for validation and information
ARRAY_TOPIC_INFO = {
    "/ESP32_GIZ/led_state_topic": {
        "length": 3,
        "labels": ["Red", "Green", "Blue"]
    },
    "/array_topic": {
        "length": 6,
        "labels": ["Val 0", "Val 1", "Val 2", "Val 3", "Val 4", "Val 5"]
    },
    # Add more topics here as needed
}


def load_saved_commands() -> Dict[str, Any]:
    """
    Load saved ROS2 commands from persistent storage file.
    
    Returns:
        Dictionary mapping topic names to lists of saved commands.
        Returns empty dict if file doesn't exist or on error.
    """
    try:
        if os.path.exists(SAVED_COMMANDS_FILE):
            with open(SAVED_COMMANDS_FILE, "r") as f:
                return json.load(f)
        return {}
    except Exception as exc:
        logger.error("Error loading saved commands: %s", exc)
        return {}


def save_commands_to_file(commands: Dict[str, Any]) -> None:
    """
    Persist ROS2 commands to JSON file.
    
    Args:
        commands: Dictionary of commands to save
    
    Raises:
        Exception: If file write operation fails
    """
    try:
        with open(SAVED_COMMANDS_FILE, "w") as f:
            json.dump(commands, f, indent=2)
    except Exception as exc:
        logger.error("Error saving commands: %s", exc)
        raise


def _construct_message(MsgClass: Any, msg_name: str, value: Any) -> Any:
    """
    Dynamically construct a ROS2 message instance from type and value.
    
    Handles common message types with automatic type conversion:
    - String, numeric types (Int8-64, UInt8-64, Float32/64), Bool
    - MultiArray types for integers and floats
    - Twist messages for robot velocity control
    - Generic messages via dict unpacking
    
    Args:
        MsgClass: The message class to instantiate
        msg_name: Simple name of the message type (e.g., "String", "Int32")
        value: Value to populate the message (type varies)
    
    Returns:
        Populated message instance ready for publishing
        
    Raises:
        HTTPException: For invalid message construction
    """
    msg = None
    
    # Handle String messages
    if msg_name == "String":
        from std_msgs.msg import String as StringMsg
        msg = StringMsg()
        msg.data = str(value)
    
    # Handle integer message types
    elif msg_name in ["Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16", "UInt32", "UInt64"]:
        msg = MsgClass()
        msg.data = int(value)
    
    # Handle float message types
    elif msg_name in ["Float32", "Float64"]:
        msg = MsgClass()
        msg.data = float(value)
    
    # Handle Bool messages
    elif msg_name == "Bool":
        from std_msgs.msg import Bool as BoolMsg
        msg = BoolMsg()
        msg.data = bool(value) if isinstance(value, bool) else (str(value).lower() in ["true", "1", "yes"])
    
    # Handle integer MultiArray types
    elif msg_name in ["Int8MultiArray", "Int16MultiArray", "Int32MultiArray", "Int64MultiArray"]:
        msg = MsgClass()
        if isinstance(value, str):
            value = json.loads(value)
        msg.data = [int(v) for v in value] if isinstance(value, list) else [int(value)]
    
    # Handle float MultiArray types
    elif msg_name in ["Float32MultiArray", "Float64MultiArray"]:
        msg = MsgClass()
        if isinstance(value, str):
            value = json.loads(value)
        msg.data = [float(v) for v in value] if isinstance(value, list) else [float(value)]
    
    # Handle Twist messages (robot velocity commands)
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
                detail="Twist message requires dict with linear_x, angular_z, etc."
            )
    
    # Generic handling for unknown types - try to construct from dict or set data field
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


@router.get("/ros/topics")
async def get_ros_topics() -> Dict[str, Any]:
    """
    Get list of all available ROS2 topics.
    
    Returns:
        Dictionary with 'topics' key containing list of topic names
        
    Raises:
        HTTPException: If ROS node not initialized or query fails
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        topic_names_and_types = ros_node.get_topic_names_and_types()
        # Just return list of names
        topics = [name for name, _ in topic_names_and_types]
        return {"topics": topics}
    except Exception as exc:
        logger.error("Error getting topics: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ros/publish")
async def publish_to_topic(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Dynamically publish a message to any ROS2 topic.
    
    Automatically resolves topic type and constructs appropriate message.
    Creates publishers on-demand and caches them for reuse.
    
    Request body should contain:
        - topic: str - Topic name to publish to
        - value: Any - Message value (format depends on message type)
    
    Returns:
        Success response with published topic, type, and value
        
    Raises:
        HTTPException: For missing parameters, unknown topics, or publish failures
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        topic = body.get("topic")
        value = body.get("value")
        
        if not topic:
            raise HTTPException(status_code=400, detail="Missing topic")
        
        # Resolve topic type from active ROS2 graph
        topic_list = ros_node.get_topic_names_and_types()
        topic_type = None
        for tname, ttypes in topic_list:
            if tname == topic:
                topic_type = ttypes[0] if ttypes else None
                break
        
        if not topic_type:
            raise HTTPException(status_code=404, detail=f"Topic {topic} not found")
        
        # Parse message type string (e.g., "std_msgs/msg/String" -> ("std_msgs", "String"))
        parts = topic_type.split("/")
        if len(parts) >= 3:
            pkg = parts[0]
            msg_name = parts[2]
        else:
            raise HTTPException(status_code=400, detail=f"Invalid topic type format: {topic_type}")
        
        # Dynamically import message class
        try:
            mod = importlib.import_module(f"{pkg}.msg")
            MsgClass = getattr(mod, msg_name)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to import message type {pkg}.msg.{msg_name}: {exc}"
            )
        
        # Construct message from value
        msg = _construct_message(MsgClass, msg_name, value)
        
        # Create or retrieve cached publisher
        if not hasattr(ros_node, "custom_publishers"):
            ros_node.custom_publishers = {}
            
        pub_key = f"{topic}_{topic_type}"
        if pub_key not in ros_node.custom_publishers:
            ros_node.custom_publishers[pub_key] = ros_node.create_publisher(MsgClass, topic, 10)
        
        # Publish the message
        ros_node.custom_publishers[pub_key].publish(msg)
        
        logger.info("Published to %s (type: %s): %s", topic, topic_type, value)
        return {"status": "success", "topic": topic, "type": topic_type, "value": value}
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error publishing to topic: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/ros/saved_commands")
async def get_saved_commands() -> Dict[str, Any]:
    """
    Retrieve all saved ROS2 commands.
    
    Returns:
        Dictionary with 'commands' key containing saved command data
    """
    try:
        commands = load_saved_commands()
        return {"commands": commands}
    except Exception as exc:
        logger.error("Error getting saved commands: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/ros/saved_commands")
async def save_command(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Save a ROS2 command for quick reuse.
    
    Allows saving commonly-used topic publish operations for one-click execution.
    Replaces existing command with same name for the topic.
    Enforces single default command per topic.
    
    Request body:
        - topic: str - Topic name
        - name: str - Unique command name
        - value: Any - Command value
        - type: str - Message type
        - isDefault: bool - Whether this should be the default auto-loaded command
        - labels: List[str] - Optional labels for array inputs
    
    Returns:
        Success confirmation message
    """
    try:
        topic = body.get("topic")
        name = body.get("name")
        value = body.get("value")
        msg_type = body.get("type")
        
        if not topic or not name:
            raise HTTPException(status_code=400, detail="Missing topic or name")
        
        commands = load_saved_commands()
        
        # Initialize topic list if needed
        if topic not in commands:
            commands[topic] = []
        
        # Remove existing command with same name (update operation)
        commands[topic] = [cmd for cmd in commands[topic] if cmd.get("name") != name]
        
        # Single default enforcement: If this command is default, unset default on others
        is_default = body.get("isDefault", False)
        if is_default:
            for cmd in commands[topic]:
                cmd["isDefault"] = False

        # Add new command
        commands[topic].append({
            "name": name,
            "value": value,
            "type": msg_type,
            "isDefault": is_default,
            "labels": body.get("labels", [])
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
    Delete a saved ROS2 command.
    
    Request body:
        - topic: str - Topic name
        - name: str - Command name to delete
    
    Returns:
        Success confirmation message
        
    Raises:
        HTTPException: If topic or command not found
    """
    try:
        topic = body.get("topic")
        name = body.get("name")
        
        if not topic or not name:
            raise HTTPException(status_code=400, detail="Missing topic or name")
        
        commands = load_saved_commands()
        
        if topic in commands:
            commands[topic] = [cmd for cmd in commands[topic] if cmd.get("name") != name]
            # Clean up empty topic lists
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


@router.get("/ros2/topics")
def list_ros2_topics(name: str = None) -> Dict[str, Any]:
    """
    List ROS2 topics with their message types.
    
    Args:
        name: Optional - if provided, returns info for just that topic
    
    Returns:
        List of topics with names and types, or single topic if filtered
        
    Raises:
        HTTPException: If ROS node not initialized or topic not found
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        topic_list = ros_node.get_topic_names_and_types()
        topics = []
        for tname, ttypes in topic_list:
            topics.append({"name": tname, "type": ttypes[0] if ttypes else "unknown"})
        
        # Filter by name if provided
        if name:
            for t in topics:
                if t["name"] == name:
                    return {"name": t["name"], "type": t["type"]}
            raise HTTPException(status_code=404, detail="Topic not found")
        
        return {"topics": topics}
    except Exception as exc:
        logger.error("Error listing ROS2 topics: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/ros2/topic_info")
def ros2_topic_info(name: str) -> Dict[str, Any]:
    """
    Get detailed information about a specific ROS2 topic.
    
    Returns topic name, type, and optional array length for known array topics.
    
    Args:
        name: Topic name to query
    
    Returns:
        Topic information dict with name, type, and optional array_length
        
    Raises:
        HTTPException: If ROS node not initialized or topic not found
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        topic_list = ros_node.get_topic_names_and_types()
        for tname, ttypes in topic_list:
            if tname == name:
                info = {"name": tname, "type": ttypes[0] if ttypes else "unknown"}
                # Add array length and labels for known array topics
                if tname in ARRAY_TOPIC_INFO:
                     info["array_length"] = ARRAY_TOPIC_INFO[tname]["length"]
                     info["labels"] = ARRAY_TOPIC_INFO[tname].get("labels", [])
                return info
        raise HTTPException(status_code=404, detail="Topic not found")
    except Exception as exc:
        logger.error("Error in /ros2/topic_info: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# UI Config for Array Buttons
SAVED_UI_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "..", "saved_ui_config.json")

def load_ui_config() -> Dict[str, Any]:
    if not os.path.exists(SAVED_UI_CONFIG_FILE):
        return {}
    try:
        with open(SAVED_UI_CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading UI config: {e}")
        return {}

def save_ui_config_to_file(config: Dict[str, Any]):
    try:
        with open(SAVED_UI_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving UI config: {e}")
        raise

@router.get("/ros/ui_config")
def get_ui_config(topic: str = None):
    config = load_ui_config()
    if topic:
        return config.get(topic, {})
    return config

@router.post("/ros/ui_config")
def save_ui_config(body: Dict[str, Any] = Body(...)):
    """
    Save UI configuration for a topic (e.g., button configs per index).
    Body: { "topic": "/foo", "config": { "0": {"label": "X", "value": 10}, ... } }
    """
    topic = body.get("topic")
    new_conf = body.get("config")
    if not topic or new_conf is None:
         raise HTTPException(status_code=400, detail="Missing topic or config")
    
    full_config = load_ui_config()
    full_config[topic] = new_conf
    save_ui_config_to_file(full_config)
    return {"status": "success", "topic": topic}

# -----------------------------------------------------------------------------
# Science Dashboard Layout
# -----------------------------------------------------------------------------
SCIENCE_LAYOUT_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "science_layout.json"))

def load_science_layout_file() -> Dict[str, Any]:
    if not os.path.exists(SCIENCE_LAYOUT_FILE):
        logger.warning(f"Science layout file not found at {SCIENCE_LAYOUT_FILE}, returning empty defaults")
        return {"groups": []}
    try:
        with open(SCIENCE_LAYOUT_FILE, "r") as f:
            data = json.load(f)
            logger.info(f"Loaded science layout from {SCIENCE_LAYOUT_FILE}: {len(data.get('groups', []))} groups")
            return data
    except Exception as e:
        logger.error(f"Error loading Science Layout from {SCIENCE_LAYOUT_FILE}: {e}")
        return {"groups": []}

def save_science_layout_file(layout: Dict[str, Any]):
    try:
        logger.info(f"Saving science layout to {SCIENCE_LAYOUT_FILE} with {len(layout.get('groups', []))} groups")
        with open(SCIENCE_LAYOUT_FILE, "w") as f:
            json.dump(layout, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        logger.info("Science layout saved successfully")
    except Exception as e:
        logger.error(f"Error saving Science Layout to {SCIENCE_LAYOUT_FILE}: {e}")
        raise

@router.get("/ros/science_layout")
def get_science_layout():
    """Get the saved layout for Science Dashboard."""
    return load_science_layout_file()

@router.post("/ros/science_layout")
def save_science_layout(body: Dict[str, Any] = Body(...)):
    """
    Save the entire Science Dashboard layout.
    Body should be the full layout object: { "groups": [...] }
    """
    save_science_layout_file(body)
    return {"status": "success", "message": "Layout saved"}
