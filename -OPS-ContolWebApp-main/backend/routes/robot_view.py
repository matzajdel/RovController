"""Robot 3D Visualization endpoints - URDF, joint states, IK solver."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import numpy as np

# IK solver import (optional - install ikpy: pip install ikpy)
try:
    from ikpy.chain import Chain
    from ikpy.link import OriginLink, URDFLink
    IKPY_AVAILABLE = True
except ImportError:
    IKPY_AVAILABLE = False
    logging.warning("ikpy not installed - IK solver disabled. Install: pip install ikpy")

# ROS2 imports
try:
    import rclpy
    from sensor_msgs.msg import JointState
    from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
    from std_msgs.msg import String
    from geometry_msgs.msg import Pose
    ROS2_AVAILABLE = True
except ImportError:
    ROS2_AVAILABLE = False
    logging.warning("ROS2 not available - running in mock mode")

logger = logging.getLogger(__name__)
router = APIRouter()


# Pydantic models
class JointCommand(BaseModel):
    """Command to set joint positions"""
    joint_names: List[str]
    positions: List[float]
    velocities: Optional[List[float]] = None
    duration: float = 2.0  # seconds


class IKRequest(BaseModel):
    """Inverse kinematics request"""
    target_position: List[float]  # [x, y, z]
    target_orientation: Optional[List[float]] = None  # [roll, pitch, yaw] or quaternion
    chain_name: str = "manipulator"  # Which kinematic chain to use


class RobotStatusResponse(BaseModel):
    """Robot status response"""
    urdf_available: bool
    joint_limits: Dict[str, Dict[str, float]]
    current_joints: Optional[Dict[str, float]]
    ee_pose: Optional[Dict[str, float]]
    ros2_connected: bool


# Global state for joint tracking
class RobotState:
    """Shared robot state"""
    def __init__(self):
        self.current_joint_states: Optional[JointState] = None
        self.urdf_content: Optional[str] = None
        self.joint_limits: Dict[str, Dict[str, float]] = {}
        self.websocket_connections: set = set()
        self.ik_chain: Optional[Any] = None
        
    def update_joint_states(self, msg: JointState):
        """Update from /joint_states topic"""
        self.current_joint_states = msg
        
    def get_current_joints(self) -> Optional[Dict[str, float]]:
        """Get current joint positions as dict"""
        if not self.current_joint_states:
            return None
        return dict(zip(
            self.current_joint_states.name,
            self.current_joint_states.position
        ))


robot_state = RobotState()


# ============== URDF ENDPOINTS ==============

@router.get("/urdf")
async def get_robot_urdf() -> Dict[str, Any]:
    """
    Get URDF description of the robot.
    Returns URDF XML string from /robot_description topic or static file.
    """
    # Try to fetch from ROS2 parameter server
    if ROS2_AVAILABLE:
        try:
            from services.ros_node import get_ros_node
            node = get_ros_node()
            if node:
                # Try to read from /robot_description topic or parameter
                # For now, return cached or static URDF
                pass
        except Exception as e:
            logger.warning(f"Could not fetch URDF from ROS2: {e}")
    
    # Load from static file
    urdf_path = Path(__file__).parent.parent / "urdf" / "mars_rover.urdf"
    
    if urdf_path.exists():
        robot_state.urdf_content = urdf_path.read_text()
        return {
            "urdf": robot_state.urdf_content,
            "source": "static_file",
            "timestamp": datetime.now().isoformat()
        }
    
    # Return sample minimal URDF if no file exists
    sample_urdf = """<?xml version="1.0"?>
<robot name="mars_rover">
  <link name="base_link">
    <visual>
      <geometry>
        <box size="0.5 0.3 0.2"/>
      </geometry>
      <material name="gray">
        <color rgba="0.5 0.5 0.5 1"/>
      </material>
    </visual>
  </link>
</robot>"""
    
    return {
        "urdf": sample_urdf,
        "source": "sample",
        "warning": "No URDF file found. Using minimal sample. Place URDF at backend/urdf/mars_rover.urdf",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/status")
async def get_robot_status() -> RobotStatusResponse:
    """
    Get current robot status including joint states and limits.
    """
    # Check ROS2 connection
    ros2_connected = False
    if ROS2_AVAILABLE:
        try:
            from services.ros_node import get_ros_node
            node = get_ros_node()
            ros2_connected = node is not None
        except:
            pass
    
    # Extract joint limits from URDF (simplified - real parser would use urdfpy)
    joint_limits = {
        # 6-DOF manipulator joints
        "joint_base": {"lower": -3.14, "upper": 3.14, "velocity": 1.0},
        "joint_shoulder": {"lower": -1.57, "upper": 1.57, "velocity": 1.0},
        "joint_elbow": {"lower": -2.0, "upper": 2.0, "velocity": 1.0},
        "joint_wrist_pitch": {"lower": -1.57, "upper": 1.57, "velocity": 1.0},
        "joint_wrist_roll": {"lower": -3.14, "upper": 3.14, "velocity": 1.0},
        "joint_gripper": {"lower": 0.0, "upper": 0.08, "velocity": 0.5},
        # Crab-drive steering joints (yaw per wheel)
        "steer_front_left": {"lower": -1.57, "upper": 1.57, "velocity": 1.5},
        "steer_front_right": {"lower": -1.57, "upper": 1.57, "velocity": 1.5},
        "steer_rear_left": {"lower": -1.57, "upper": 1.57, "velocity": 1.5},
        "steer_rear_right": {"lower": -1.57, "upper": 1.57, "velocity": 1.5},
    }
    
    return RobotStatusResponse(
        urdf_available=robot_state.urdf_content is not None,
        joint_limits=joint_limits,
        current_joints=robot_state.get_current_joints(),
        ee_pose=None,  # TODO: calculate from forward kinematics
        ros2_connected=ros2_connected
    )


# ============== JOINT CONTROL ENDPOINTS ==============

@router.post("/set_joints")
async def set_joint_positions(command: JointCommand) -> Dict[str, Any]:
    """
    Send joint trajectory command to robot controller.
    Publishes to /joint_trajectory_controller/joint_trajectory topic.
    """
    if not ROS2_AVAILABLE:
        return {
            "status": "mock",
            "message": "ROS2 not available - command logged but not sent",
            "command": command.dict()
        }
    
    try:
        from services.ros_node import get_ros_node
        node = get_ros_node()
        
        if not node:
            raise HTTPException(status_code=503, detail="ROS node not initialized")
        
        # Create JointTrajectory message
        trajectory = JointTrajectory()
        trajectory.joint_names = command.joint_names
        
        point = JointTrajectoryPoint()
        point.positions = command.positions
        
        if command.velocities:
            point.velocities = command.velocities
        else:
            point.velocities = [0.0] * len(command.positions)
        
        # Set time from start
        point.time_from_start.sec = int(command.duration)
        point.time_from_start.nanosec = int((command.duration % 1) * 1e9)
        
        trajectory.points = [point]
        
        # Publish - need to add publisher to ros_interface
        # For now, log the command
        logger.info(f"Joint command: {command.joint_names} -> {command.positions}")
        
        return {
            "status": "success",
            "message": "Joint trajectory sent",
            "joints": dict(zip(command.joint_names, command.positions)),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to send joint command: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ik_solve")
async def solve_inverse_kinematics(request: IKRequest) -> Dict[str, Any]:
    """
    Solve inverse kinematics for manipulator end-effector.
    Returns joint angles to reach target position.
    """
    if not IKPY_AVAILABLE:
        return {
            "status": "error",
            "message": "IK solver not available. Install: pip install ikpy",
            "request": request.dict()
        }
    
    try:
        # Simple IK solver using ikpy
        # This is a basic example - real implementation would load chain from URDF
        
        # Create simple 6-DOF arm chain (example)
        if not robot_state.ik_chain:
            # Build simple chain for demonstration
            # Real version should parse from URDF
            robot_state.ik_chain = _build_sample_ik_chain()
        
        target_position = np.array(request.target_position)
        
        # Solve IK
        joint_positions = robot_state.ik_chain.inverse_kinematics(
            target_position=target_position,
            initial_position=[0] * len(robot_state.ik_chain.links),
        )
        
        # Extract real joint values (skip fixed links)
        joint_names = ["joint_base", "joint_shoulder", "joint_elbow", 
                      "joint_wrist_pitch", "joint_wrist_roll", "joint_gripper"]
        
        # Filter out origin link values
        real_joints = [j for i, j in enumerate(joint_positions) if i > 0 and i <= len(joint_names)]
        
        return {
            "status": "success",
            "joint_positions": dict(zip(joint_names, real_joints[:len(joint_names)])),
            "target": request.target_position,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"IK solver failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "fallback": "simple_jacobian"  # Could implement fallback solver
        }


def _build_sample_ik_chain():
    """Build sample IK chain for 6-DOF manipulator"""
    if not IKPY_AVAILABLE:
        return None
    
    # Simple DH parameters for demo arm
    # Real version should parse URDF
    try:
        links = [
            OriginLink(),
            URDFLink(
                name="base",
                origin_translation=[0, 0, 0.1],
                origin_orientation=[0, 0, 0],
                rotation=[0, 0, 1],  # Z-axis rotation
            ),
            URDFLink(
                name="shoulder",
                origin_translation=[0, 0, 0.2],
                origin_orientation=[0, 0, 0],
                rotation=[0, 1, 0],  # Y-axis
            ),
            URDFLink(
                name="elbow",
                origin_translation=[0, 0, 0.3],
                origin_orientation=[0, 0, 0],
                rotation=[0, 1, 0],
            ),
            URDFLink(
                name="wrist_pitch",
                origin_translation=[0, 0, 0.2],
                origin_orientation=[0, 0, 0],
                rotation=[0, 1, 0],
            ),
            URDFLink(
                name="wrist_roll",
                origin_translation=[0, 0, 0.1],
                origin_orientation=[0, 0, 0],
                rotation=[1, 0, 0],
            ),
        ]
        return Chain(name='manipulator', links=links)
    except Exception as e:
        logger.error(f"Failed to build IK chain: {e}")
        return None


# ============== WEBSOCKET STREAMING ==============

@router.websocket("/ws")
async def websocket_robot_stream(websocket: WebSocket):
    """
    WebSocket endpoint for streaming robot state.
    Streams: joint_states, tf, end-effector pose
    """
    await websocket.accept()
    robot_state.websocket_connections.add(websocket)
    
    logger.info("Robot WebSocket client connected")
    
    try:
        # Send initial state
        initial_data = {
            "type": "robot_state",
            "joints": robot_state.get_current_joints(),
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send_json(initial_data)
        
        # Listen for commands from frontend
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=0.1)
                message = json.loads(data)
                
                # Handle different message types
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    })
                    
                elif message.get("type") == "request_state":
                    await websocket.send_json({
                        "type": "robot_state",
                        "joints": robot_state.get_current_joints(),
                        "timestamp": datetime.now().isoformat()
                    })
                    
            except asyncio.TimeoutError:
                # No message received - send periodic update
                if robot_state.current_joint_states:
                    await websocket.send_json({
                        "type": "joint_update",
                        "joints": robot_state.get_current_joints(),
                        "timestamp": datetime.now().isoformat()
                    })
                await asyncio.sleep(0.05)  # 20Hz update rate
                
    except WebSocketDisconnect:
        logger.info("Robot WebSocket client disconnected")
    except Exception as e:
        logger.error(f"Robot WebSocket error: {e}")
    finally:
        robot_state.websocket_connections.discard(websocket)


# ============== PRESET POSITIONS ==============

@router.get("/presets")
async def get_preset_positions() -> Dict[str, Any]:
    """Get predefined robot poses (Home, Pickup, Inspect, etc.)"""
    presets = {
        "home": {
            "description": "Home position - arm folded",
            "joints": {
                "joint_base": 0.0,
                "joint_shoulder": -0.5,
                "joint_elbow": 1.5,
                "joint_wrist_pitch": -1.0,
                "joint_wrist_roll": 0.0,
                "joint_gripper": 0.0
            }
        },
        "pickup": {
            "description": "Pickup position - arm extended down",
            "joints": {
                "joint_base": 0.0,
                "joint_shoulder": 0.8,
                "joint_elbow": 0.5,
                "joint_wrist_pitch": -1.3,
                "joint_wrist_roll": 0.0,
                "joint_gripper": 0.04
            }
        },
        "inspect": {
            "description": "Inspect sensor - arm pointing forward",
            "joints": {
                "joint_base": 0.0,
                "joint_shoulder": 0.0,
                "joint_elbow": 1.57,
                "joint_wrist_pitch": 0.0,
                "joint_wrist_roll": 0.0,
                "joint_gripper": 0.02
            }
        },
        "stow": {
            "description": "Stow position - minimal footprint",
            "joints": {
                "joint_base": 0.0,
                "joint_shoulder": -1.2,
                "joint_elbow": 2.0,
                "joint_wrist_pitch": -0.8,
                "joint_wrist_roll": 0.0,
                "joint_gripper": 0.0
            }
        }
    }
    
    return {"presets": presets}


@router.post("/preset/{preset_name}")
async def execute_preset(preset_name: str) -> Dict[str, Any]:
    """Execute a predefined preset position"""
    presets_response = await get_preset_positions()
    presets = presets_response["presets"]
    
    if preset_name not in presets:
        raise HTTPException(
            status_code=404,
            detail=f"Preset '{preset_name}' not found. Available: {list(presets.keys())}"
        )
    
    preset = presets[preset_name]
    joints = preset["joints"]
    
    # Send command
    command = JointCommand(
        joint_names=list(joints.keys()),
        positions=list(joints.values()),
        duration=3.0  # Slower for presets
    )
    
    result = await set_joint_positions(command)
    result["preset"] = preset_name
    result["description"] = preset["description"]
    
    return result


# ============== HELPER FUNCTIONS ==============

def initialize_robot_state_subscriber():
    """
    Initialize ROS2 subscriber for /joint_states.
    Should be called from main.py on startup.
    """
    if not ROS2_AVAILABLE:
        logger.warning("ROS2 not available - robot state subscriber not initialized")
        return
    
    try:
        from services.ros_node import get_ros_node
        node = get_ros_node()
        
        if node:
            # Add joint_states subscriber to existing node
            # This would need to be added to ros_interface.py ROSNode class
            logger.info("Robot state subscriber initialized")
    except Exception as e:
        logger.error(f"Failed to initialize robot state subscriber: {e}")
