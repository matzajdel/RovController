#!/usr/bin/env python3
"""
OPS Control WebApp Backend Server
FastAPI server with ROS 2 integration for robot control
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional
import threading
import subprocess
import time

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor

from geometry_msgs.msg import Twist, Vector3
from sensor_msgs.msg import Joy
from std_msgs.msg import String, Bool
from std_msgs.msg import Int32MultiArray, Int8MultiArray
from std_msgs.msg import Float32MultiArray, Float64MultiArray

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Path, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import evdev
from evdev import ecodes

logger = logging.getLogger("main")
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class JoystickCommand(BaseModel):
    """Joystick command data model"""
    x: float
    y: float
    timestamp: Optional[str] = None

class RobotStatus(BaseModel):
    """Robot status data model"""
    connected: bool
    last_command: Optional[Dict[str, Any]] = None
    last_update: str

class ROSNode(Node):
    """ROS 2 Node for robot communication"""
    
    def __init__(self):
        super().__init__('ops_control_backend')
        
        # Publisher - only cmd_vel_nav topic
        self.cmd_vel_publisher = self.create_publisher(Twist, '/cmd_vel_nav', 10)
        # Publisher na /array_topic (Float32MultiArray)
        self.array_topic_publisher = self.create_publisher(Float64MultiArray, '/array_topic', 10)
        # Publisher na /ESP8_GIZ/led_state_topic (Int32MultiArray)
        self.led_state_publisher = self.create_publisher(Int8MultiArray, '/ESP32_GIZ/led_state_topic', 10)
        self.button_array_length = 6  # 6 przycisków/elementów w tablicy
        self.array_state = [0.0] * self.button_array_length  # Domyślnie wszystkie 0
        
        # Status tracking
        self.robot_connected = True  # Assume connected for cmd_vel operation
        self.last_command = None
        self.last_update = datetime.now().isoformat()
        self.joystick_active = False  # Track if joystick is being used
        
        # WebSocket connections
        self.websocket_connections = set()
        
        # Send initial stop command on startup
        self.publish_stop()
        
        logger.info("ROS Node initialized with /cmd_vel_nav publisher")
    
    def publish_cmd_vel(self, linear_x: float, angular_z: float):
        """Publish velocity command to /cmd_vel_nav"""
        try:
            twist = Twist()
            twist.linear = Vector3(x=linear_x, y=0.0, z=0.0)
            twist.angular = Vector3(x=0.0, y=0.0, z=angular_z)
            
            self.cmd_vel_publisher.publish(twist)
            
            self.last_command = {
                'type': 'cmd_vel_nav',
                'linear_x': linear_x,
                'angular_z': angular_z
            }
            self.last_update = datetime.now().isoformat()
            
            logger.debug(f"Published cmd_vel_nav: linear_x={linear_x}, angular_z={angular_z}")
        except Exception as e:
            logger.error(f"Error publishing cmd_vel_nav: {e}")
    
    def publish_stop(self):
        """Publish stop command (0,0,0) to /cmd_vel_nav"""
        try:
            twist = Twist()
            twist.linear = Vector3(x=0.0, y=0.0, z=0.0)
            twist.angular = Vector3(x=0.0, y=0.0, z=0.0)
            
            self.cmd_vel_publisher.publish(twist)
            
            self.last_command = {
                'type': 'stop',
                'linear_x': 0.0,
                'angular_z': 0.0
            }
            self.last_update = datetime.now().isoformat()
            
            logger.debug("Published STOP command to cmd_vel_nav")
        except Exception as e:
            logger.error(f"Error publishing stop command: {e}")
    
    def set_joystick_active(self, active: bool):
        """Set joystick active state and send stop if deactivated"""
        self.joystick_active = active
        if not active:
            self.publish_stop()
            logger.info("Joystick deactivated - sent stop command")
    
    def publish_joystick(self, x: float, y: float):
        """Convert joystick input to velocity commands and publish to /cmd_vel_nav"""
        try:
            # Set joystick as active
            self.joystick_active = True
            # Ustaw LED na Joystick
            self.publish_led_state([1, 0, 0])
            # Convert joystick input to velocity commands
            linear_x = y * 1.0  # Max forward/backward speed
            angular_z = -x * 1.0  # Max rotation speed (negative for correct direction)
            
            self.publish_cmd_vel(linear_x, angular_z)
            
            self.last_command = {
                'type': 'joystick_to_cmd_vel_nav',
                'joystick_x': x,
                'joystick_y': y,
                'linear_x': linear_x,
                'angular_z': angular_z
            }
            self.last_update = datetime.now().isoformat()
        except Exception as e:
            logger.error(f"Error processing joystick input: {e}")
    
    def handle_joystick_release(self):
        """Handle joystick release - send stop command"""
        try:
            self.publish_stop()
            logger.info("Joystick released - sent stop command")
        except Exception as e:
            logger.error(f"Error handling joystick release: {e}")
    
    async def broadcast_to_websockets(self, message: dict):
        """Broadcast message to all connected WebSocket clients"""
        if not self.websocket_connections:
            return
            
        disconnected = set()
        for websocket in self.websocket_connections.copy():
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"Failed to send message to WebSocket client: {e}")
                disconnected.add(websocket)
        
        # Remove disconnected WebSockets
        self.websocket_connections -= disconnected
    
    def add_websocket(self, websocket: WebSocket):
        """Add WebSocket connection"""
        self.websocket_connections.add(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.websocket_connections)}")
    
    def remove_websocket(self, websocket: WebSocket):
        """Remove WebSocket connection"""
        self.websocket_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.websocket_connections)}")
    
    def get_status(self) -> RobotStatus:
        """Get current robot status"""
        return RobotStatus(
            connected=self.robot_connected,
            last_command=self.last_command,
            last_update=self.last_update
        )
    
    def publish_array_topic(self, button_id: int):
        """Publikuj tablicę z 1 na pozycji button_id-1, reszta 0"""
        try:
            arr = [0] * self.button_array_length
            if 1 <= button_id <= self.button_array_length:
                arr[button_id-1] = 1
            msg = Int32MultiArray()
            msg.data = arr
            self.array_topic_publisher.publish(msg)
            logger.info(f"Published to /array_topic: {arr}")
        except Exception as e:
            logger.error(f"Error publishing to /array_topic: {e}")
    
    def set_array_topic(self, button_id: int, value: float):
        """Ustaw wartość na danym indeksie (100 lub -100), reszta bez zmian"""
        try:
            idx = button_id - 1
            if 0 <= idx < self.button_array_length:
                self.array_state[idx] = value
                msg = Float64MultiArray()
                msg.data = self.array_state.copy()
                self.array_topic_publisher.publish(msg)
                logger.info(f"Published to /array_topic: {self.array_state}")
        except Exception as e:
            logger.error(f"Error publishing to /array_topic: {e}")
    
    def publish_led_state(self, state: list):
        """Publish LED state to /ESP32_GIZ/led_state_topic"""
        try:
            msg = Int8MultiArray()
            msg.data = state
            self.led_state_publisher.publish(msg)
            logger.info(f"Published to /ESP32_GIZ/led_state_topic: {state}")
        except Exception as e:
            logger.error(f"Error publishing to /ESP32_GIZ/led_state_topic: {e}")

class GamepadManager:
    def __init__(self):
        self.devices = []
        self.active_index = None
        self.scan_gamepads()
        self.listener_thread = None
        self.listener_active = False
        self.callback = None

    def scan_gamepads(self):
        self.devices = [evdev.InputDevice(path) for path in evdev.list_devices() if 'event' in path and 'js' not in path]

    def list_gamepads(self):
        return [f"{d.name} ({d.path})" for d in self.devices]

    def set_active(self, idx, callback):
        self.active_index = idx
        self.callback = callback
        if self.listener_thread and self.listener_thread.is_alive():
            self.listener_active = False
            self.listener_thread.join()
        self.listener_active = True
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()

    def _listen_loop(self):
        if self.active_index is None or self.active_index >= len(self.devices):
            return
        dev = self.devices[self.active_index]
        for event in dev.read_loop():
            if not self.listener_active:
                break
            if event.type == evdev.ecodes.EV_ABS or event.type == evdev.ecodes.EV_KEY:
                if self.callback:
                    self.callback(event)

    def stop(self):
        self.listener_active = False
        if self.listener_thread:
            self.listener_thread.join()

# Global ROS node instance
ros_node: Optional[ROSNode] = None
ros_executor: Optional[MultiThreadedExecutor] = None
ros_thread: Optional[threading.Thread] = None

# globalny mnożnik prędkości dla pada
pad_speed_multiplier = 1.0

def init_ros():
    """Initialize ROS 2"""
    global ros_node, ros_executor, ros_thread
    
    try:
        rclpy.init()
        ros_node = ROSNode()
        ros_executor = MultiThreadedExecutor()
        ros_executor.add_node(ros_node)
        
        # Run ROS in separate thread
        ros_thread = threading.Thread(target=ros_executor.spin, daemon=True)
        ros_thread.start()
        
        logger.info("ROS 2 initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize ROS 2: {e}")
        raise

def shutdown_ros():
    """Shutdown ROS 2"""
    global ros_node, ros_executor, ros_thread
    
    try:
        if ros_executor:
            ros_executor.shutdown()
        if ros_node:
            ros_node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        logger.info("ROS 2 shutdown complete")
    except Exception as e:
        logger.error(f"Error during ROS 2 shutdown: {e}")

# FastAPI app
app = FastAPI(
    title="OPS Control WebApp Backend",
    description="Backend API server for OPS Control WebApp with ROS 2 integration",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gamepad manager instance
gamepad_manager = GamepadManager()

@app.on_event("startup")
async def startup_event():
    """Application startup"""
    logger.info("Starting OPS Control WebApp Backend...")
    init_ros()

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown"""
    logger.info("Shutting down OPS Control WebApp Backend...")
    shutdown_ros()

<<<<<<< Updated upstream
=======

# Register all route modules
app.include_router(gamepad.router, tags=["gamepad"])
app.include_router(gps.router, tags=["gps"])
app.include_router(vision.router, prefix="/vision", tags=["vision"])
app.include_router(ros_topics.router, tags=["ros_topics"])

>>>>>>> Stashed changes
@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "OPS Control WebApp Backend", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "ros_connected": ros_node is not None,
        "robot_connected": ros_node.robot_connected if ros_node else False
    }

@app.get("/status", response_model=RobotStatus)
async def get_robot_status():
    """Get robot status"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    return ros_node.get_status()

@app.post("/joystick")
async def joystick_command(command: JoystickCommand):
    """Send joystick command"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        ros_node.publish_joystick(command.x, command.y)
        return {
            "status": "success",
            "command": command.dict(),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error processing joystick command: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/cmd_vel")
async def velocity_command(linear_x: float, angular_z: float):
    """Send velocity command"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        ros_node.publish_cmd_vel(linear_x, angular_z)
        return {
            "status": "success",
            "linear_x": linear_x,
            "angular_z": angular_z,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error processing velocity command: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/stop")
async def emergency_stop():
    """Emergency stop - send zero velocities and set LED state to Off"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_stop()
        ros_node.publish_led_state([0, 0, 1])  # Dodatkowo ustaw LED na Off
        return {
            "status": "success",
            "message": "Emergency stop executed and LED set to Off",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error executing emergency stop: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/joystick/activate")
async def activate_joystick():
    """Activate joystick mode"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        ros_node.set_joystick_active(True)
        return {
            "status": "success",
            "message": "Joystick activated",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error activating joystick: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/joystick/deactivate")
async def deactivate_joystick():
    """Deactivate joystick mode and send stop"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        ros_node.set_joystick_active(False)
        return {
            "status": "success",
            "message": "Joystick deactivated and robot stopped",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error deactivating joystick: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/joystick/release")
async def joystick_release():
    """Handle joystick release - send stop command"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        ros_node.handle_joystick_release()
        return {
            "status": "success",
            "message": "Joystick released and robot stopped",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error handling joystick release: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/topic_array/button1")
async def topic_array_button1():
    """Handle button 1 press - publish to /topic_array"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_array_topic(1)
        return {"status": "success", "button": 1, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error publishing array_topic button1: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/topic_array/button2")
async def topic_array_button2():
    """Handle button 2 press - publish to /topic_array"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_array_topic(2)
        return {"status": "success", "button": 2, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error publishing array_topic button2: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/topic_array/button3")
async def topic_array_button3():
    """Handle button 3 press - publish to /topic_array"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_array_topic(3)
        return {"status": "success", "button": 3, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error publishing array_topic button3: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/array_topic/{button_id}")
async def array_topic_button(button_id: int = Path(..., ge=1, le=6), body: dict = None):
    """Handle button press - publish to /array_topic and toggle value"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        value = body.get("value") if body else None
        if value not in [100, 0, -100]:
            raise HTTPException(status_code=400, detail="Value must be 100 or -100")
        ros_node.set_array_topic(button_id, float(value))
        return {"status": "success", "button": button_id, "value": value, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        logger.error(f"Error publishing array_topic button{button_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/led/off")
async def led_off():
    """Turn LED off"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_led_state([1, 0, 0])
        return {"status": "success", "led_state": [1, 0, 0]}
    except Exception as e:
        logger.error(f"Error setting LED Off: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/led/joystick")
async def led_joystick():
    """Set LED state for joystick activation"""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.publish_led_state([0, 0, 1])
        return {"status": "success", "led_state": [0, 0, 1]}
    except Exception as e:
        logger.error(f"Error setting LED Joystick: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    
    if ros_node:
        ros_node.add_websocket(websocket)
    
    try:
        # Send initial status
        if ros_node:
            initial_status = {
                "type": "status",
                "data": ros_node.get_status().dict(),
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send_text(json.dumps(initial_status))
        
        while True:
            # Listen for messages from client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                
                if message.get("type") == "joystick" and ros_node:
                    ros_node.publish_joystick(
                        message.get("x", 0.0),
                        message.get("y", 0.0)
                    )
                elif message.get("type") == "joystick_release" and ros_node:
                    ros_node.handle_joystick_release()
                elif message.get("type") == "joystick_activate" and ros_node:
                    ros_node.set_joystick_active(True)
                elif message.get("type") == "joystick_deactivate" and ros_node:
                    ros_node.set_joystick_active(False)
                elif message.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }))
                    
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received: {data}")
            except Exception as e:
                logger.error(f"Error processing WebSocket message: {e}")
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if ros_node:
            ros_node.remove_websocket(websocket)

@app.get("/gamepads")
def list_gamepads():
    """List available gamepads"""
    gamepad_manager.scan_gamepads()
    return {"gamepads": gamepad_manager.list_gamepads()}

class GamepadSelect(BaseModel):
    index: int

@app.post("/gamepads/select")
def select_gamepad(sel: GamepadSelect):
    """Select and activate a gamepad by index"""
    # Mapowanie: (przycisk, indeks, wartość)
    button_to_array = {
        ecodes.BTN_WEST: (1, 100),   # Y -> 1, 100
        ecodes.BTN_EAST: (1, -100),   # B -> 1, -100
        ecodes.BTN_NORTH: (2, 100),    # X -> 2, 100
        ecodes.BTN_SOUTH: (2, -100),  # A -> 2, -100
        ecodes.BTN_DPAD_UP: (3, 100),
        ecodes.BTN_DPAD_RIGHT: (4, -100),
        ecodes.BTN_DPAD_DOWN: (3, 100),
        ecodes.BTN_DPAD_LEFT: (4, -100),
        ecodes.BTN_THUMBL: (5, 100),
        ecodes.BTN_THUMBR: (5, -100)
    }
    axis_values = {ecodes.ABS_Z: 0.0, ecodes.ABS_RZ: 0.0, ecodes.ABS_GAS: 0.0, ecodes.ABS_BRAKE: 0.0}
    button_states = {ecodes.BTN_TL: 0, ecodes.BTN_TR: 0}
    def on_event(event):
        nonlocal axis_values, button_states
        global pad_speed_multiplier
        # Triggery
        if event.type == ecodes.EV_ABS:
            # Obsługa triggerów dla różnych padów
            if event.code in [ecodes.ABS_Z, ecodes.ABS_RZ, ecodes.ABS_GAS, ecodes.ABS_BRAKE]:
                axis_values[event.code] = event.value
                logger.info(f"Trigger values: ABS_Z={axis_values.get(ecodes.ABS_Z, 0.0)}, ABS_RZ={axis_values.get(ecodes.ABS_RZ, 0.0)}, GAS={axis_values.get(ecodes.ABS_GAS, 0.0)}, BRAKE={axis_values.get(ecodes.ABS_BRAKE, 0.0)}")
            # DPAD jako ABS_HAT0Y i ABS_HAT0X
            if event.code == ecodes.ABS_HAT0Y:
                if event.value == -1:
                    v = 100
                elif event.value == 1:
                    v = -100
                else:
                    v = 0
                if ros_node:
                    ros_node.set_array_topic(3, float(v))
            elif event.code == ecodes.ABS_HAT0X:
                if event.value == 1:
                    v = 100
                elif event.value == -1:
                    v = -100
                else:
                    v = 0
                if ros_node:
                    ros_node.set_array_topic(4, float(v))
            # ...cmd_vel_nav z obsługą różnych triggerów...
            if ros_node:
                # Preferuj GAS/BRAKE jeśli obecne, w innym wypadku ABS_Z/ABS_RZ
                left_trigger = axis_values.get(ecodes.ABS_BRAKE, None)
                right_trigger = axis_values.get(ecodes.ABS_GAS, None)
                if left_trigger is not None and right_trigger is not None:
                    # Normalizuj do 0..1 (przyjmując zakres 0..1023)
                    left_trigger = left_trigger / 1023.0
                    right_trigger = right_trigger / 1023.0
                else:
                    left_trigger = axis_values.get(ecodes.ABS_Z, 0.0)
                    right_trigger = axis_values.get(ecodes.ABS_RZ, 0.0)
                    left_trigger = left_trigger / 255.0
                    right_trigger = right_trigger / 255.0
                reverse_left = button_states.get(ecodes.BTN_TL, 0)
                reverse_right = button_states.get(ecodes.BTN_TR, 0)
                left = left_trigger * (-1 if reverse_left else 1)
                right = right_trigger * (-1 if reverse_right else 1)
                linear_x = (left + right) / 2.0 * pad_speed_multiplier
                angular_z = (left - right) / 2.0 * pad_speed_multiplier
                ros_node.publish_cmd_vel(linear_x, angular_z)
        elif event.type == ecodes.EV_KEY:
            if event.code in [ecodes.BTN_TL, ecodes.BTN_TR]:
                button_states[event.code] = event.value
            # Każdy przycisk niezależnie
            if event.code in button_to_array:
                idx, val = button_to_array[event.code]
                if event.value in (1, 2):
                    v = val
                else:
                    v = 0
                if ros_node:
                    ros_node.set_array_topic(idx, float(v))
    gamepad_manager.set_active(sel.index, on_event)
    return {"status": "selected", "index": sel.index}

@app.post("/gamepads/stop")
def stop_gamepad():
    """Stop the active gamepad"""
    gamepad_manager.stop()
    return {"status": "stopped"}

@app.get("/bluetooth/scan")
def bluetooth_scan():
    try:
        # Start bluetoothctl as a subprocess for longer scan
        scan_proc = subprocess.Popen(['bluetoothctl'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        scan_proc.stdin.write('scan on\n')
        scan_proc.stdin.flush()
        time.sleep(2)  # Scan for 8 seconds
        scan_proc.stdin.write('devices\n')
        scan_proc.stdin.flush()
        time.sleep(1)
        scan_proc.stdin.write('scan off\nquit\n')
        scan_proc.stdin.flush()
        out, _ = scan_proc.communicate(timeout=5)
        devices = []
        for line in out.splitlines():
            if line.strip().startswith('Device'):
                parts = line.strip().split(' ', 2)
                if len(parts) == 3:
                    _, mac, name = parts
                    devices.append({"mac": mac, "name": name})
        return {"devices": devices}
    except Exception as e:
        return {"error": str(e)}

class BluetoothPairRequest(BaseModel):
    mac: str

@app.post("/bluetooth/pair")
def bluetooth_pair(req: BluetoothPairRequest):
    try:
        # Pair with device
        pair_cmd = f"echo 'pair {req.mac}\nquit' | bluetoothctl"
        pair_result = subprocess.check_output(pair_cmd, shell=True, text=True)
        logger.info(f"PAIR OUTPUT:\n{pair_result}")
        # Trust device
        trust_cmd = f"echo 'trust {req.mac}\nquit' | bluetoothctl"
        trust_result = subprocess.check_output(trust_cmd, shell=True, text=True)
        logger.info(f"TRUST OUTPUT:\n{trust_result}")
        # Try to connect up to 3 times
        connected = False
        connect_outputs = []
        for _ in range(3):
            connect_cmd = f"echo 'connect {req.mac}\nquit' | bluetoothctl"
            connect_result = subprocess.check_output(connect_cmd, shell=True, text=True)
            connect_outputs.append(connect_result)
            logger.info(f"CONNECT OUTPUT:\n{connect_result}")
            if "Connection successful" in connect_result or "Connection already exists" in connect_result:
                connected = True
                break
            time.sleep(2)
        status = "paired_and_connected" if connected else "paired_but_not_connected"
        return {
            "status": status,
            "mac": req.mac,
            "pair_result": pair_result,
            "trust_result": trust_result,
            "connect_outputs": connect_outputs
        }
    except Exception as e:
        logger.error(f"Bluetooth pair error: {e}")
        return {"error": str(e)}

@app.get("/bluetooth/mobile")
def bluetooth_mobile_wip():
    """Endpoint for mobile bluetooth - WiP"""
    return {"status": "WiP", "message": "Bluetooth mobile endpoint is Work in Progress (WiP)"}

@app.get("/bluetooth/mobile/wip-frontend")
def bluetooth_mobile_wip_frontend():
    """Endpoint for mobile bluetooth frontend - WiP"""
    return {"status": "WiP", "message": "Bluetooth mobile frontend is Work in Progress (WiP)"}

@app.post("/run_gamepad_bridge")
def run_gamepad_bridge():
    try:
        # Check if already running
        check_cmd = "pgrep -f 'gamepad_ros2_bridge.py'"
        already_running = subprocess.call(check_cmd, shell=True) == 0
        if already_running:
            return {"status": "already_running"}
        # Start the gamepad_ros2_bridge.py process in the background
        subprocess.Popen(["python3", "/home/arkadiuszubnt/Desktop/LR/-OPS-ContolWebApp/gamepad_ros2_bridge.py", "--port", "65432"])
        return {"status": "started"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/kill_gamepad_bridge")
def kill_gamepad_bridge():
    try:
        # Find and kill the process listening on port 65432
        kill_cmd = "sudo kill -9 $(sudo lsof -i :65432 -t)"
        subprocess.call(kill_cmd, shell=True)
        return {"status": "killed"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/bluetooth_jetson/speed")
def set_bluetooth_jetson_speed(body: dict):
    global pad_speed_multiplier
    value = body.get("speed")
    try:
        pad_speed_multiplier = float(value)
        return {"status": "success", "speed": pad_speed_multiplier}
    except Exception as e:
        return {"error": str(e)}

@app.get("/bluetooth_jetson/speed")
def get_bluetooth_jetson_speed():
    global pad_speed_multiplier
    return {"speed": pad_speed_multiplier}

@app.get("/ros2/topics")
def list_ros2_topics(name: str = None):
    """List available ROS2 topics and their types. If name is given, return type for that topic only."""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        topic_list = ros_node.get_topic_names_and_types()
        topics = []
        for tname, ttypes in topic_list:
            topics.append({"name": tname, "type": ttypes[0] if ttypes else "unknown"})
        if name:
            for t in topics:
                if t["name"] == name:
                    return {"name": t["name"], "type": t["type"]}
            raise HTTPException(status_code=404, detail="Topic not found")
        return {"topics": topics}
    except Exception as e:
        logger.error(f"Error listing ROS2 topics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ros2/publish")
def ros2_publish(body: dict = Body(...)):
    """Publish a message to a ROS2 topic. Expects {topic, type, value} in body."""
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        topic = body.get("topic")
        msg_type = body.get("type")
        value = body.get("value")
        if not topic or not msg_type or value is None:
            raise HTTPException(status_code=400, detail="Missing topic, type, or value")
        # Dynamically import the message type
        import importlib
        pkg, msg = msg_type.split("/")
        mod = importlib.import_module(f"{pkg}_msgs.msg")
        MsgClass = getattr(mod, msg)
        # Parse value (should be JSON string or dict)
        if isinstance(value, str):
            import json as _json
            value = _json.loads(value)
        msg_obj = MsgClass(**value)
        pub = ros_node.create_publisher(MsgClass, topic, 10)
        pub.publish(msg_obj)
        return {"status": "published", "topic": topic, "type": msg_type, "value": value}
    except Exception as e:
        logger.error(f"Error publishing to ROS2 topic: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Add a mapping for known array topics

if __name__ == "__main__":
    # Get configuration from environment variables
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "2137"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
    
    # Run the server
    uvicorn.run(
        "main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level=LOG_LEVEL
    )
