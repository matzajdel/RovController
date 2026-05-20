"""WebSocket endpoint for real-time communication."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.ros_node import get_ros_node

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    ros_node = get_ros_node()
    if ros_node:
        ros_node.add_websocket(websocket)
    try:
        if ros_node:
            initial_status = {
                "type": "status",
                "data": ros_node.get_status(),
                "timestamp": datetime.now().isoformat(),
            }
            await websocket.send_text(json.dumps(initial_status))
        while True:
            data = await websocket.receive_text()
            node = get_ros_node()
            if not node:
                continue
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON received: %s", data)
                continue
            message_type = message.get("type")
            if message_type == "joystick":
                x = message.get("x")
                y = message.get("y")
                node.publish_joystick(float(x) if x is not None else 0.0, float(y) if y is not None else 0.0)
            elif message_type == "joystick_release":
                node.handle_joystick_release()
            elif message_type == "joystick_activate":
                node.set_joystick_active(True)
            elif message_type == "joystick_deactivate":
                node.set_joystick_active(False)
            elif message_type == "ping":
                await websocket.send_text(
                    json.dumps({"type": "pong", "timestamp": datetime.now().isoformat()})
                )
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("WebSocket error: %s", exc)
    finally:
        node = get_ros_node()
        if node:
            node.remove_websocket(websocket)
