"""Science watcher endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from services.ros_node import get_ros_node
from models import ScienceWatcherRequest

router = APIRouter(prefix="/science")


@router.post("/watchers")
def add_science_watcher(req: ScienceWatcherRequest) -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        ros_node.add_science_watcher(req.topic, req.frequency_hz, req.max_points)
        return {"status": "ok", "watchers": ros_node.list_science_watchers()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive logging
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/watchers")
def remove_science_watcher(topic: str = Query(...)) -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        removed = ros_node.remove_science_watcher(topic)
        return {"status": "ok", "removed": removed}
    except Exception as exc:  # pragma: no cover - defensive logging
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/watchers")
def list_science_watchers() -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    return {"watchers": ros_node.list_science_watchers()}


@router.get("/data")
def get_science_data(topic: str = Query(...)) -> dict[str, object]:
    ros_node = get_ros_node()
    if not ros_node:
        raise HTTPException(status_code=503, detail="ROS node not initialized")
    try:
        return {"topic": topic, "data": ros_node.get_science_data(topic)}
    except Exception as exc:  # pragma: no cover - defensive logging
        raise HTTPException(status_code=500, detail=str(exc)) from exc
