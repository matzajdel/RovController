"""ROS 2 screen and script management endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from models import ScreenRunRequest, ScreenKillRequest, ScriptPayload
from service_registry import screen_manager

router = APIRouter(prefix="/ros2")


@router.get("/screens")
def list_ros2_screens() -> dict[str, object]:
    try:
        screens = screen_manager.list_active_screens()
        return {"screens": screens, "timestamp": datetime.now().isoformat()}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/screens/run")
def run_ros2_screen(req: ScreenRunRequest) -> dict[str, object]:
    try:
        if req.script_name:
            result = screen_manager.run_script(
                req.script_name,
                session_override=req.session,
                working_dir_override=req.working_dir,
                auto_restart_override=req.auto_restart,
                command_override=req.command,
            )
        else:
            if not req.command:
                raise HTTPException(status_code=400, detail="command is required when script_name is not provided")
            result = screen_manager.run_custom(
                command=req.command,
                session=req.session,
                working_dir=req.working_dir,
                auto_restart=req.auto_restart,
            )
        return {"status": "ok", "result": result}
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/screens/kill")
def kill_ros2_screen(req: ScreenKillRequest) -> dict[str, object]:
    try:
        result = screen_manager.kill_session(req.session)
        return {"status": "ok", "result": result}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/screens/logs/{session}")
def get_ros2_screen_log(session: str, lines: int = Query(200, ge=1, le=2000)) -> dict[str, object]:
    try:
        tail = screen_manager.tail_log(session, lines)
        return {"status": "ok", **tail}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/scripts")
def get_ros2_scripts() -> dict[str, object]:
    scripts = screen_manager.list_scripts()
    return {"scripts": scripts}


@router.post("/scripts")
def create_or_update_ros2_script(payload: ScriptPayload) -> dict[str, object]:
    try:
        script = screen_manager.add_or_update_script(payload.dict())
        return {"status": "ok", "script": script, "scripts": screen_manager.list_scripts()}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/scripts/{name}")
def delete_ros2_script(name: str) -> dict[str, object]:
    removed = screen_manager.remove_script(name)
    if not removed:
        raise HTTPException(status_code=404, detail="Script not found")
    return {"status": "ok", "scripts": screen_manager.list_scripts()}
