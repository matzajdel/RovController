"""Basic informational endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

from services.ros_node import get_ros_node
from models import RobotStatus

router = APIRouter()


@router.get("/")
async def root() -> dict[str, str]:
    return {"message": "OPS Control WebApp Backend", "version": "1.0.0"}


@router.get("/health")
async def health_check() -> dict[str, object]:
    ros_node = get_ros_node()
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "ros_connected": ros_node is not None,
        "robot_connected": ros_node.robot_connected if ros_node else False,
    }


@router.get("/status", response_model=RobotStatus)
async def get_robot_status() -> RobotStatus:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    status_dict = ros_node.get_status()
    return RobotStatus(**status_dict)
