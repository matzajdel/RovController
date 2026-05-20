"""GPS destination coordinates route handlers."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.ros_node import get_ros_node
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class GPSDestination(BaseModel):
    """GPS destination coordinates model"""
    lat: float
    lon: float


@router.post("/gps/destination")
async def send_gps_destination(coords: GPSDestination):
    """Send GPS destination coordinates to ROS topic /gps_waypoint
    
    Args:
        coords: GPS coordinates with lat and lon
        
    Returns:
        Success response with coordinates and topic name
        
    Raises:
        HTTPException: If ROS node not initialized or publishing fails
    """
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    
    try:
        ros_node.publish_gps_destination(coords.lon, coords.lat)
        return {
            "status": "success",
            "lat": coords.lat,
            "lon": coords.lon,
            "topic": "/gps_waypoint"
        }
    except Exception as e:
        logger.error(f"Error publishing GPS destination: {e}")
        raise HTTPException(status_code=500, detail=str(e))
