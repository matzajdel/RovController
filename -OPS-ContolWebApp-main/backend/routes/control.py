"""Robot control endpoints (velocity, joystick, arrays, LEDs)."""
from __future__ import annotations

import logging

 

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Path

from services.ros_node import get_ros_node
from models import JoystickCommand, TwistFull

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/joystick")
async def joystick_command(command: JoystickCommand) -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_joystick(command.x, command.y)
        return {
            "status": "success",
            "command": command.dict(),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cmd_vel")
async def velocity_command(linear_x: float, angular_z: float) -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_cmd_vel(linear_x, angular_z)
        return {
            "status": "success",
            "linear_x": linear_x,
            "angular_z": angular_z,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cmd_vel_full")
async def velocity_command_full(twist: TwistFull) -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_twist_full(twist)
        return {
            "status": "success",
            "twist": twist.dict(),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/cmd_vel/publishing")
async def set_cmd_vel_publishing(enabled: bool) -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    ros_node.set_twist_publishing(enabled)
    return {"status": "success", "enabled": enabled}


@router.post("/stop")
async def emergency_stop() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_stop()
        ros_node.publish_led_state([1, 0, 0])
        ros_node.publish_rgb(200.0, 200.0, 200.0)
        return {
            "status": "success",
            "message": "Emergency stop executed and LED set to Off",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/joystick/activate")
async def activate_joystick() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.set_joystick_active(True)
        return {
            "status": "success",
            "message": "Joystick activated",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/joystick/deactivate")
async def deactivate_joystick() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.set_joystick_active(False)
        return {
            "status": "success",
            "message": "Joystick deactivated and robot stopped",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/joystick/release")
async def joystick_release() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.handle_joystick_release()
        return {
            "status": "success",
            "message": "Joystick released and robot stopped",
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/topic_array/button1")
async def topic_array_button1() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_array_topic(1)
        return {"status": "success", "button": 1, "timestamp": datetime.now().isoformat()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/topic_array/button2")
async def topic_array_button2() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_array_topic(2)
        return {"status": "success", "button": 2, "timestamp": datetime.now().isoformat()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/topic_array/button3")
async def topic_array_button3() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_array_topic(3)
        return {"status": "success", "button": 3, "timestamp": datetime.now().isoformat()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/array_topic/{button_id}")
async def array_topic_button(
    *,
    button_id: int = Path(..., ge=1, le=6),
    body: Optional[dict[str, float]] = None,
) -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        raw_value = body.get("value") if body else None
        if raw_value is None:
            raise HTTPException(status_code=400, detail="Missing 'value' in request body")

        try:
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Value must be a number") from exc

        # Accept dynamic manipulator values while keeping a safe command range.
        if value < -100 or value > 100:
            raise HTTPException(status_code=400, detail="Value must be in range -100 to 100")

        ros_node.set_array_topic(button_id, value)
        return {
            "status": "success",
            "button": button_id,
            "value": value,
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/arrow_keys")
async def arrow_keys(
    body: dict[str, object],
) -> dict[str, object]:
    """Publish Int32MultiArray to the arrow_keys topic.

    Expects JSON body: {"data": [1, 90], "topic": "/dupatest"}
    The optional "topic" field switches the publisher to a new ROS 2
    topic at runtime (created automatically if it doesn't exist yet).
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        # Switch topic if requested
        topic = body.get("topic")
        if topic and isinstance(topic, str):
            ros_node.set_arrow_keys_topic(topic)

        data = body.get("data", [])
        if not isinstance(data, list) or len(data) != 2:
            raise HTTPException(status_code=400, detail="data must be a 2-element array")
        ros_node.publish_arrow_keys([int(v) for v in data])
        return {
            "status": "success",
            "data": data,
            "topic": ros_node.current_arrow_keys_topic,
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/custom_topic")
async def publish_custom_topic(
    body: dict[str, object],
) -> dict[str, object]:
    """Publish to any topic with a chosen array message type (created on-demand).

    Expects JSON body:
        topic    (str)  – ROS 2 topic name, e.g. "/Serwa"
        data     (list) – array of numbers, e.g. [1, 90]
        msg_type (str)  – optional, one of:
                          "Int8MultiArray", "Int16MultiArray",
                          "Int32MultiArray" (default), "Int64MultiArray",
                          "UInt8MultiArray", "UInt16MultiArray",
                          "UInt32MultiArray", "UInt64MultiArray",
                          "Float32MultiArray", "Float64MultiArray"

        --- Partial update mode (optional) ---
        update_index (int)  – if provided, only update this index in the
                              last-known array for the topic. 'data' should
                              be a single-element list [value]. All other
                              indices keep their previous values.

    The publisher is created automatically the first time a topic + type
    combination is used and cached for subsequent calls.
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        topic = body.get("topic")
        data = body.get("data", [])
        msg_type_name = body.get("msg_type", "Int32MultiArray")
        update_index = body.get("update_index")

        if not topic or not isinstance(topic, str):
            raise HTTPException(status_code=400, detail="Missing or invalid 'topic'")
        if not isinstance(data, list):
            raise HTTPException(status_code=400, detail="'data' must be an array")

        if not topic.startswith("/"):
            topic = f"/{topic}"

        # /array_topic is pre-declared in ROSNode as Float64MultiArray.
        # Publishing another type to the same topic can fail in ROS 2.
        if topic == "/array_topic" and msg_type_name != "Float64MultiArray":
            msg_type_name = "Float64MultiArray"

        # Resolve the message class from std_msgs
        import std_msgs.msg as std_msgs_mod
        ALLOWED_TYPES = {
            "Int8MultiArray", "Int16MultiArray",
            "Int32MultiArray", "Int64MultiArray",
            "UInt8MultiArray", "UInt16MultiArray",
            "UInt32MultiArray", "UInt64MultiArray",
            "Float32MultiArray", "Float64MultiArray",
        }
        if msg_type_name not in ALLOWED_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported msg_type '{msg_type_name}'. Allowed: {sorted(ALLOWED_TYPES)}",
            )
        MsgClass = getattr(std_msgs_mod, msg_type_name)

        # Lazy-create publishers keyed by (topic, type)
        if not hasattr(ros_node, "_custom_pubs"):
            ros_node._custom_pubs = {}
        if not hasattr(ros_node, "_custom_topic_state"):
            ros_node._custom_topic_state = {}

        pub_key = f"{topic}__{msg_type_name}"
        if pub_key not in ros_node._custom_pubs:
            ros_node._custom_pubs[pub_key] = ros_node.create_publisher(MsgClass, topic, 10)
            logger.info("Created %s publisher for %s", msg_type_name, topic)

        is_float = "Float" in msg_type_name
        cast = float if is_float else int

        # Partial update mode: merge with last-known array state
        if update_index is not None:
            update_index = int(update_index)
            if len(data) < 1:
                raise HTTPException(status_code=400, detail="'data' must have at least 1 element for partial update")
            new_value = data[0]
            current_arr = ros_node._custom_topic_state.get(pub_key, [])
            # Extend if needed
            while len(current_arr) <= update_index:
                current_arr.append(0)
            current_arr[update_index] = cast(new_value)
            data = list(current_arr)
        else:
            data = [cast(v) for v in data]

        # Remember the last published state for this topic
        ros_node._custom_topic_state[pub_key] = list(data)

        # Build and publish message
        msg = MsgClass()
        msg.data = [cast(v) for v in data]
        ros_node._custom_pubs[pub_key].publish(msg)

        logger.info("Published %s to %s: %s", msg_type_name, topic, data)
        return {
            "status": "success",
            "topic": topic,
            "msg_type": msg_type_name,
            "data": [cast(v) for v in data],
            "timestamp": datetime.now().isoformat(),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/led/off")
async def led_off() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_led_state([1, 0, 0])
        return {"status": "success", "led_state": [1, 0, 0]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/led/joystick")
async def led_joystick() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_led_state([0, 1, 0])
        return {"status": "success", "led_state": [0, 1, 0]}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
