"""ROS 2 node implementation and lifecycle helpers."""
from __future__ import annotations

import importlib
import io
import json
import logging
import os
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import rclpy
from fastapi import WebSocket
from geometry_msgs.msg import Twist, Vector3
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from sensor_msgs.msg import Joy
from std_msgs.msg import Float32MultiArray, Int32MultiArray, Float64MultiArray
from utils.topic_condition import check_topic_condition

logger = logging.getLogger(__name__)


class ROSNode(Node):
    """ROS 2 Node for robot communication."""

    def __init__(self) -> None:
        super().__init__("ops_control_backend")

        # Dynamic cmd_vel topic (can be changed at runtime)
        self.current_cmd_vel_topic = "/cmd_vel"
        self.cmd_vel_publisher = self.create_publisher(Twist, self.current_cmd_vel_topic, 10)
        self.array_topic_publisher = self.create_publisher(Float64MultiArray, "/array_topic", 10)
        self.led_state_publisher = self.create_publisher(Int32MultiArray, "/ESP32_GIZ/led_state_topic", 10)
        self.rgb_publisher = self.create_publisher(Float32MultiArray, "/rgb", 10)
        self.gamepad_publisher = self.create_publisher(Joy, "gamepad_input", 10)
        self.gps_waypoint_publisher = self.create_publisher(Float64MultiArray, "/gps_waypoint", 10)
        self.current_arrow_keys_topic = "/arrow_keys"
        self.arrow_keys_publisher = self.create_publisher(Int32MultiArray, self.current_arrow_keys_topic, 10)

        self.button_array_length = 6
        self.array_state = [0.0] * self.button_array_length

        self.robot_connected = True
        self.last_command: Optional[Dict[str, Any]] = None
        self.last_update = datetime.now().isoformat()
        self.joystick_active = False

        self.websocket_connections: Set[WebSocket] = set()

        # Continuous twist publishing (enabled only while steering is active)
        self._latest_twist = Twist()
        self._twist_publishing_enabled: bool = False
        self._twist_timer = self.create_timer(1.0 / 10.0, self._twist_timer_callback)

        logger.info("ROS Node initialized with %s publisher (250Hz timer)", self.current_cmd_vel_topic)

        self.science_watchers: Dict[str, Dict[str, Any]] = {}
        self.science_xml_path = os.path.join(os.path.dirname(__file__), "..", "data", "science_config.xml")
        self._science_last_xml_save = 0.0

        # High-frequency keepalive to push duplicate points to graphs if publishers are silent
        self._science_keepalive_timer = self.create_timer(0.1, self._science_watchers_keepalive)

        # Retry pending (unresolved) science watchers every 5 s
        self._pending_retry_timer = self.create_timer(5.0, self._retry_pending_watchers)

    def set_cmd_vel_topic(self, topic_name: str) -> str:
        """Switch the cmd_vel publisher to a different ROS 2 topic at runtime."""
        # Normalise: ensure leading slash
        if not topic_name.startswith("/"):
            topic_name = f"/{topic_name}"
        if topic_name == self.current_cmd_vel_topic:
            logger.info("cmd_vel topic already set to %s", topic_name)
            return self.current_cmd_vel_topic
        try:
            # Destroy old publisher and create a new one
            self.destroy_publisher(self.cmd_vel_publisher)
            self.cmd_vel_publisher = self.create_publisher(Twist, topic_name, 10)
            old_topic = self.current_cmd_vel_topic
            self.current_cmd_vel_topic = topic_name
            logger.info("cmd_vel publisher switched: %s → %s", old_topic, topic_name)
        except Exception as exc:
            logger.error("Failed to switch cmd_vel topic to %s: %s", topic_name, exc)
        return self.current_cmd_vel_topic

    def _resolve_ros_type(self, topic: str) -> Optional[Tuple[str, Any]]:
        names_and_types = self.get_topic_names_and_types()
        msg_type_str: Optional[str] = None
        for name, types in names_and_types:
            if name == topic and types:
                msg_type_str = types[0]
                break
        if not msg_type_str:
            return None
        try:
            pkg, _, msg_name = msg_type_str.partition("/msg/")
            module = importlib.import_module(f"{pkg}.msg")
            msg_cls = getattr(module, msg_name)
            return msg_type_str, msg_cls
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to resolve message class for %s: %s", msg_type_str, exc)
            return None

    @staticmethod
    def _extract_value(msg: Any) -> Any:
        if hasattr(msg, "data"):
            val = msg.data
            # Convert array.array or similar structures to list for JSON serialization
            if hasattr(val, "tolist"):
                return val.tolist()
            elif hasattr(val, "__iter__") and not isinstance(val, (str, bytes, dict)):
                return list(val)
            return val
        
        # Support Twist (geometry_msgs)
        if hasattr(msg, "linear") and hasattr(msg, "angular"):
            return {
                "linear": {
                    "x": getattr(msg.linear, "x", 0.0),
                    "y": getattr(msg.linear, "y", 0.0),
                    "z": getattr(msg.linear, "z", 0.0)
                },
                "angular": {
                    "x": getattr(msg.angular, "x", 0.0),
                    "y": getattr(msg.angular, "y", 0.0),
                    "z": getattr(msg.angular, "z", 0.0)
                }
            }
            
        return str(msg)

    def add_science_watcher(self, topic: str, frequency_hz: float, max_points: int) -> None:
        freq = max(0.001, float(frequency_hz))
        max_pts = max(1, int(max_points))

        # If watcher already exists, update its settings with the max requested
        if topic in self.science_watchers:
            watcher = self.science_watchers[topic]
            watcher["frequency_hz"] = max(watcher.get("frequency_hz", freq), freq)
            new_max_pts = max(watcher.get("max_points", max_pts), max_pts)
            watcher["max_points"] = new_max_pts
            # Trim buffer if new limit is smaller
            if len(watcher["buffer"]) > new_max_pts:
                del watcher["buffer"][: len(watcher["buffer"]) - new_max_pts]
            # If it was pending, try to resolve now
            if watcher.get("pending"):
                self._try_activate_watcher(topic)
            self._save_science_xml()
            return

        # Try to resolve the topic type
        resolved = self._resolve_ros_type(topic)
        if not resolved:
            # Topic not yet active — register as pending watcher
            logger.info("Science watcher for %s registered as pending (topic not yet active)", topic)
            self.science_watchers[topic] = {
                "topic": topic,
                "type": None,
                "frequency_hz": freq,
                "max_points": max_pts,
                "buffer": [],
                "subscription": None,
                "pending": True,
                "last_store_time": 0.0,
                "last_msg_time": 0.0,
            }
            self._save_science_xml()
            return

        self._activate_watcher(topic, resolved, freq, max_pts, [])

    def _activate_watcher(
        self,
        topic: str,
        resolved: Tuple[str, Any],
        freq: float,
        max_pts: int,
        existing_buffer: List[Dict[str, Any]],
    ) -> None:
        """Create a live ROS subscription for a science watcher."""
        type_str, msg_cls = resolved
        buffer: List[Dict[str, Any]] = existing_buffer
        
        # Pull forward the existing last_store_time if present, or base it on now
        watcher = self.science_watchers.get(topic, {})
        last_store_time = watcher.get("last_store_time", time.time())
        last_msg_time = watcher.get("last_msg_time", 0.0)
        self.science_watchers.setdefault(topic, {})["last_store_time"] = last_store_time
        self.science_watchers.setdefault(topic, {})["last_msg_time"] = last_msg_time

        def callback(msg: Any) -> None:
            try:
                now = time.time()
                # Access the latest global tracker so timers and callbacks share state
                w = self.science_watchers.get(topic)
                if not w: return
                last_msg_t = w.get("last_msg_time", 0.0)
                 
                if now - last_msg_t < (1.0 / freq):
                    return
                w["last_msg_time"] = now
                w["last_store_time"] = now
                value = self._extract_value(msg)
                buffer.append({"timestamp": datetime.now().isoformat(), "value": value})
                if len(buffer) > max_pts:
                    del buffer[: len(buffer) - max_pts]
                if now - self._science_last_xml_save > 5.0:
                    self._save_science_xml()
                    self._science_last_xml_save = now
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Science watcher callback error for %s: %s", topic, exc)

        subscription = self.create_subscription(msg_cls, topic, callback, 10)
        self.science_watchers[topic] = {
            "topic": topic,
            "type": type_str,
            "frequency_hz": freq,
            "max_points": max_pts,
            "buffer": buffer,
            "subscription": subscription,
            "pending": False,
            "last_store_time": last_store_time,
            "last_msg_time": last_msg_time,
        }
        logger.info("Science watcher activated for %s (type=%s)", topic, type_str)
        self._save_science_xml()

    def _try_activate_watcher(self, topic: str) -> bool:
        """Attempt to activate a pending watcher. Returns True if activated."""
        watcher = self.science_watchers.get(topic)
        if not watcher or not watcher.get("pending"):
            return False
        resolved = self._resolve_ros_type(topic)
        if not resolved:
            return False
        self._activate_watcher(
            topic, resolved,
            watcher["frequency_hz"],
            watcher["max_points"],
            watcher["buffer"],  # preserve any already-buffered data
        )
        return True

    def _retry_pending_watchers(self) -> None:
        """Timer callback: try to activate all pending science watchers."""
        pending = [t for t, w in list(self.science_watchers.items()) if w.get("pending")]
        for topic in pending:
            activated = self._try_activate_watcher(topic)
            if activated:
                logger.info("Pending science watcher for %s is now active", topic)

    def _science_watchers_keepalive(self) -> None:
        """Timer callback: duplicate last known value if graph frequency expired and no new ROS messages arrived."""
        now = time.time()
        for topic, watcher in list(self.science_watchers.items()):
            if watcher.get("pending"):
                continue
            
            freq = watcher.get("frequency_hz", 1.0)
            target_interval = 1.0 / freq
            last_t = watcher.get("last_store_time", 0.0)
            
            # Allow a tiny padding so the natural callback has a chance to trigger 
            # without racing the exact millisecond
            if now - last_t > (target_interval + 0.04):
                buffer = watcher.get("buffer")
                if buffer and len(buffer) > 0:
                    # Repeat the last recorded value
                    latest_entry = buffer[-1]
                    new_val = latest_entry["value"]
                    buffer.append({"timestamp": datetime.now().isoformat(), "value": new_val})
                    watcher["last_store_time"] = now
                    
                    max_pts = watcher.get("max_points", 50)
                    if len(buffer) > max_pts:
                        del buffer[: len(buffer) - max_pts]

    def remove_science_watcher(self, topic: str) -> bool:
        watcher = self.science_watchers.get(topic)
        if not watcher:
            return False
        try:
            subscription = watcher.get("subscription")
            if subscription is not None:
                self.destroy_subscription(subscription)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Error destroying subscription for %s: %s", topic, exc)
        # Ensure the watcher is fully removed from runtime state and future XML saves.
        self.science_watchers.pop(topic, None)
        self._save_science_xml()
        return True

    def wait_for_topic_sync(
        self, topic: str, expected_value: Any, condition: str = "==", timeout: float = 30.0
    ) -> bool:
        """
        Blocks until the topic receives a new message that satisfies the condition,
        or until it times out.
        Returns True if condition met, False on timeout.
        """
        resolved = self._resolve_ros_type(topic)
        if not resolved:
            logger.error("wait_for_topic_sync: Topic %s not found or unsupported", topic)
            return False
        
        _, msg_cls = resolved
        event = threading.Event()
        condition_met = [False]
        last_log_time = [0.0]

        def temp_callback(msg: Any) -> None:
            if condition_met[0]:
                return
                
            val = self._extract_value(msg)
            # Log value locally to not spam every single msg
            now = time.time()
            if now - last_log_time[0] > 1.0:
                logger.debug("wait_for_topic_sync: checking %s %s %s... (current: %s)", val, condition, expected_value, val)
                last_log_time[0] = now
                
            if check_topic_condition(val, condition, expected_value):
                condition_met[0] = True
                event.set()

        sub = self.create_subscription(msg_cls, topic, temp_callback, 10)
        logger.info("Macro started waiting for topic %s %s %s (timeout=%.1fs)", topic, condition, expected_value, timeout)
        
        try:
            event.wait(timeout)
        finally:
            # Clean up subscription
            self.destroy_subscription(sub)
            
        if condition_met[0]:
            logger.info("Macro wait condition MET for %s", topic)
        else:
            logger.warning("Macro wait condition TIMED OUT for %s", topic)
            
        return condition_met[0]

    def list_science_watchers(self) -> List[Dict[str, Any]]:
        return [
            {
                "topic": watcher["topic"],
                "type": watcher["type"],
                "frequency_hz": watcher["frequency_hz"],
                "max_points": watcher["max_points"],
                "buffer_len": len(watcher["buffer"]),
                "pending": watcher.get("pending", False),
            }
            for watcher in self.science_watchers.values()
        ]

    def get_science_data(self, topic: str) -> List[Dict[str, Any]]:
        watcher = self.science_watchers.get(topic)
        if not watcher:
            return []
        return watcher["buffer"]

    def _save_science_xml(self) -> None:
        try:
            root = ET.Element("scienceConfig")
            for topic in sorted(self.science_watchers.keys()):
                watcher = self.science_watchers[topic]
                element = ET.SubElement(root, "watcher")
                ET.SubElement(element, "topic").text = topic
                ET.SubElement(element, "type").text = watcher["type"] or ""
                ET.SubElement(element, "frequency_hz").text = str(watcher["frequency_hz"])
                ET.SubElement(element, "max_points").text = str(watcher["max_points"])
            tree = ET.ElementTree(root)

            # Serialize first and write only on content change to avoid file churn.
            buf = io.BytesIO()
            tree.write(buf, encoding="utf-8", xml_declaration=True)
            new_xml = buf.getvalue()

            if os.path.exists(self.science_xml_path):
                with open(self.science_xml_path, "rb") as fh:
                    if fh.read() == new_xml:
                        return

            with open(self.science_xml_path, "wb") as fh:
                fh.write(new_xml)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to save science XML: %s", exc)

    def load_science_xml(self) -> None:
        if not os.path.exists(self.science_xml_path):
            return
        try:
            tree = ET.parse(self.science_xml_path)
            root = tree.getroot()
            for element in root.findall("watcher"):
                topic = element.findtext("topic")
                freq = float(element.findtext("frequency_hz") or "1.0")
                max_pts = int(element.findtext("max_points") or "1")
                try:
                    self.add_science_watcher(topic, freq, max_pts)
                except Exception as exc:  # pragma: no cover - defensive logging
                    logger.warning("Skipping watcher from XML (%s): %s", topic, exc)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Failed to load science XML: %s", exc)

    def publish_cmd_vel(self, linear_x: float, angular_z: float) -> None:
        try:
            twist = Twist()
            twist.linear = Vector3(x=linear_x, y=0.0, z=0.0)
            twist.angular = Vector3(x=0.0, y=0.0, z=angular_z)
            self.cmd_vel_publisher.publish(twist)
            self.last_command = {
                "type": "cmd_vel_nav",
                "linear_x": linear_x,
                "angular_z": angular_z,
            }
            self.last_update = datetime.now().isoformat()
            logger.debug("Published cmd_vel_nav: linear_x=%s, angular_z=%s", linear_x, angular_z)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing cmd_vel_nav: %s", exc)

    def set_twist_publishing(self, enabled: bool) -> None:
        """Enable or disable the continuous cmd_vel timer."""
        self._twist_publishing_enabled = enabled
        if not enabled:
            # Zero out the stored twist so a late publish cannot move the robot
            self._latest_twist = Twist()
        logger.info("Twist publishing %s", "ENABLED" if enabled else "DISABLED")

    def _twist_timer_callback(self) -> None:
        """Called at 10 Hz — publishes only while steering is active."""
        if not self._twist_publishing_enabled:
            return
        try:
            self.cmd_vel_publisher.publish(self._latest_twist)
        except Exception as exc:  # pragma: no cover
            logger.error("twist timer error: %s", exc)

    def update_twist(
        self,
        lx: float = 0.0, ly: float = 0.0, lz: float = 0.0,
        ax: float = 0.0, ay: float = 0.0, az: float = 0.0,
    ) -> None:
        """Update the stored twist (published continuously by the timer)."""
        twist = Twist()
        twist.linear = Vector3(x=float(lx), y=float(ly), z=float(lz))
        twist.angular = Vector3(x=float(ax), y=float(ay), z=float(az))
        self._latest_twist = twist
        self.last_command = {
            "type": "cmd_vel_full",
            "linear_x": lx, "linear_y": ly, "linear_z": lz,
            "angular_x": ax, "angular_y": ay, "angular_z": az,
        }
        self.last_update = datetime.now().isoformat()

    def publish_twist_full(self, twist_payload: Any) -> None:
        try:
            self.update_twist(
                lx=float(twist_payload.linear_x),
                ly=float(twist_payload.linear_y),
                lz=float(twist_payload.linear_z),
                ax=float(twist_payload.angular_x),
                ay=float(twist_payload.angular_y),
                az=float(twist_payload.angular_z),
            )
            logger.debug("Updated twist: %s", self.last_command)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error updating twist: %s", exc)

    def publish_stop(self) -> None:
        try:
            self.update_twist(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
            self.cmd_vel_publisher.publish(self._latest_twist)
            self.last_command = {
                "type": "stop",
                "linear_x": 0.0,
                "angular_z": 0.0,
            }
            self.last_update = datetime.now().isoformat()
            logger.debug("Published STOP command to cmd_vel_nav")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing stop command: %s", exc)

    def set_joystick_active(self, active: bool) -> None:
        self.joystick_active = active
        if not active:
            self.publish_stop()
            logger.info("Joystick deactivated - sent stop command")

    def publish_joystick(self, x: float, y: float) -> None:
        try:
            self.joystick_active = True
            self.publish_led_state([0, 1, 0])
            
            safe_x = float(x) if x is not None else 0.0
            safe_y = float(y) if y is not None else 0.0
            
            linear_x = safe_y * 1.0
            angular_z = -safe_x * 1.0
            self.publish_cmd_vel(linear_x, angular_z)
            self.last_command = {
                "type": "joystick_to_cmd_vel_nav",
                "joystick_x": safe_x,
                "joystick_y": safe_y,
                "linear_x": linear_x,
                "angular_z": angular_z,
            }
            self.last_update = datetime.now().isoformat()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error processing joystick input: %s", exc)

    def handle_joystick_release(self) -> None:
        try:
            self.publish_stop()
            logger.info("Joystick released - sent stop command")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error handling joystick release: %s", exc)

    def publish_array_topic(self, button_id: int) -> None:
        try:
            payload = [0.0] * self.button_array_length
            if 1 <= button_id <= self.button_array_length:
                payload[button_id - 1] = 1.0
            message = Float64MultiArray()
            message.data = payload
            self.array_topic_publisher.publish(message)
            logger.info("Published to /array_topic: %s", payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing to /array_topic: %s", exc)

    def set_array_topic(self, button_id: int, value: float) -> None:
        try:
            idx = button_id - 1
            if 0 <= idx < self.button_array_length:
                self.array_state[idx] = value
                message = Float64MultiArray()
                message.data = self.array_state.copy()
                self.array_topic_publisher.publish(message)
                logger.info("Published to /array_topic: %s", self.array_state)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing to /array_topic: %s", exc)

    def publish_manipulator_values(self, values: List[float]) -> None:
        try:
            message = Float64MultiArray()
            message.data = [float(value) for value in values]
            self.array_topic_publisher.publish(message)
            self.last_command = {
                "type": "manipulator_array",
                "values": list(message.data),
            }
            self.last_update = datetime.now().isoformat()
            logger.debug("Published manipulator values to /array_topic: %s", message.data)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing manipulator values: %s", exc)

    def publish_led_state(self, state: List[int]) -> None:
        try:
            message = Int32MultiArray()
            message.data = state
            self.led_state_publisher.publish(message)
            logger.info("Published to /ESP32_GIZ/led_state_topic: %s", state)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing to /ESP32_GIZ/led_state_topic: %s", exc)

    def publish_rgb(self, r: float, g: float, b: float) -> None:
        """Publish RGB values to /rgb topic - order: R, G, B (0-255 each)"""
        try:
            message = Float32MultiArray()
            message.data = [r, g, b]
            self.rgb_publisher.publish(message)
            logger.info("Published to /rgb: R=%.1f, G=%.1f, B=%.1f", r, g, b)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing to /rgb: %s", exc)

    def set_arrow_keys_topic(self, topic_name: str) -> str:
        """Switch the arrow_keys publisher to a different ROS 2 topic at runtime."""
        if not topic_name.startswith("/"):
            topic_name = f"/{topic_name}"
        if topic_name == self.current_arrow_keys_topic:
            return self.current_arrow_keys_topic
        try:
            self.destroy_publisher(self.arrow_keys_publisher)
            self.arrow_keys_publisher = self.create_publisher(Int32MultiArray, topic_name, 10)
            old_topic = self.current_arrow_keys_topic
            self.current_arrow_keys_topic = topic_name
            logger.info("arrow_keys publisher switched: %s → %s", old_topic, topic_name)
        except Exception as exc:
            logger.error("Failed to switch arrow_keys topic to %s: %s", topic_name, exc)
        return self.current_arrow_keys_topic

    def publish_arrow_keys(self, data: List[int]) -> None:
        """Publish Int32MultiArray to the current arrow_keys topic."""
        try:
            message = Int32MultiArray()
            message.data = data
            self.arrow_keys_publisher.publish(message)
            logger.info("Published to %s: %s", self.current_arrow_keys_topic, data)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing to %s: %s", self.current_arrow_keys_topic, exc)

    def publish_gamepad_state(self, axes: List[float], buttons: List[int]) -> None:
        try:
            message = Joy()
            message.header.stamp = self.get_clock().now().to_msg()
            message.axes = list(axes)
            message.buttons = list(buttons)
            self.gamepad_publisher.publish(message)
            logger.debug("Published Joy message: axes=%s buttons=%s", axes, buttons)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing Joy message: %s", exc)

    def publish_gps_destination(self, lon: float, lat: float) -> None:
        """Publish GPS destination coordinates to /gps_waypoint topic."""
        try:
            message = Float64MultiArray()
            message.data = [lon, lat]
            self.gps_waypoint_publisher.publish(message)
            self.last_command = {
                "type": "gps_destination",
                "lon": lon,
                "lat": lat,
            }
            self.last_update = datetime.now().isoformat()
            logger.info("Published GPS destination to /gps_waypoint: lon=%s, lat=%s", lon, lat)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error publishing GPS destination: %s", exc)

    async def broadcast_to_websockets(self, message: Dict[str, Any]) -> None:
        if not self.websocket_connections:
            return
        disconnected: Set[WebSocket] = set()
        for websocket in self.websocket_connections.copy():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning("Failed to send message to WebSocket client: %s", exc)
                disconnected.add(websocket)
        self.websocket_connections -= disconnected

    def add_websocket(self, websocket: WebSocket) -> None:
        self.websocket_connections.add(websocket)
        logger.info("WebSocket connected. Total connections: %s", len(self.websocket_connections))

    def remove_websocket(self, websocket: WebSocket) -> None:
        self.websocket_connections.discard(websocket)
        logger.info("WebSocket disconnected. Total connections: %s", len(self.websocket_connections))

    def get_status(self) -> Dict[str, Any]:
        return {
            "connected": self.robot_connected,
            "last_command": self.last_command,
            "last_update": self.last_update,
        }


ros_node: Optional[ROSNode] = None
ros_executor: Optional[MultiThreadedExecutor] = None
ros_thread: Optional[threading.Thread] = None


def init_ros() -> None:
    global ros_node, ros_executor, ros_thread
    if ros_node is not None:
        logger.warning("ROS node already initialized, skipping")
        return
    try:
        # Only initialize if not already initialized
        if not rclpy.ok():
            rclpy.init()
        else:
            logger.warning("ROS 2 context already initialized")
            
        ros_node = ROSNode()
        ros_executor = MultiThreadedExecutor()
        ros_executor.add_node(ros_node)
        ros_thread = threading.Thread(target=ros_executor.spin, daemon=True)
        ros_thread.start()
        logger.info("ROS 2 initialised successfully")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Failed to initialise ROS 2: %s", exc)
        raise


def shutdown_ros() -> None:
    global ros_node, ros_executor, ros_thread
    try:
        if ros_executor:
            ros_executor.shutdown()
        if ros_node:
            ros_node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        ros_node = None
        ros_executor = None
        ros_thread = None
        logger.info("ROS 2 shutdown complete")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Error during ROS 2 shutdown: %s", exc)


def get_ros_node() -> Optional[ROSNode]:
    return ros_node


__all__ = ["ROSNode", "init_ros", "shutdown_ros", "get_ros_node", "ros_node"]
