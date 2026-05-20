from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
from camera_controller import camera_controller
from camera_state import CameraUpdate, build_camera_configs, normalize_camera_config

app = FastAPI(title="Vision App Backend")

# Enable CORS for the frontend React application
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for local standalone
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CAMERA_CONFIGS: Dict[str, dict] = build_camera_configs()

@app.get("/api/cameras")
def get_cameras():
    for config in CAMERA_CONFIGS.values():
        normalize_camera_config(config)
    camera_controller.sync_statuses(CAMERA_CONFIGS)
    return CAMERA_CONFIGS


@app.post("/api/cameras/rescan")
def rescan_cameras():
    CAMERA_CONFIGS.clear()
    CAMERA_CONFIGS.update(build_camera_configs())
    camera_controller.sync_statuses(CAMERA_CONFIGS)
    return CAMERA_CONFIGS

@app.put("/api/cameras/{cam_id}")
def update_camera(cam_id: str, payload: CameraUpdate):
    if cam_id not in CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    updates = payload.model_dump(exclude_unset=True)
    CAMERA_CONFIGS[cam_id].update(updates)
    normalize_camera_config(CAMERA_CONFIGS[cam_id])
    
    # If the sender is running, restart it with the new zoom-derived crop settings.
    if CAMERA_CONFIGS[cam_id].get("sender_running"):
        camera_controller.start_sender(cam_id, CAMERA_CONFIGS[cam_id])

    camera_controller.sync_statuses(CAMERA_CONFIGS)
        
    return CAMERA_CONFIGS[cam_id]

@app.post("/api/cameras/{cam_id}/sender/start")
def start_sender(cam_id: str):
    if cam_id not in CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")

    normalize_camera_config(CAMERA_CONFIGS[cam_id])
    camera_controller.start_sender(cam_id, CAMERA_CONFIGS[cam_id])
    camera_controller.sync_statuses(CAMERA_CONFIGS)
    return {"status": "sender started"}

@app.post("/api/cameras/{cam_id}/sender/stop")
def stop_sender(cam_id: str):
    if cam_id not in CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")
         
    camera_controller.stop_sender(cam_id, CAMERA_CONFIGS[cam_id])
    camera_controller.sync_statuses(CAMERA_CONFIGS)
    return {"status": "sender stopped"}
    
@app.post("/api/cameras/{cam_id}/receiver/start")
def start_receiver(cam_id: str):
    if cam_id not in CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")

    normalize_camera_config(CAMERA_CONFIGS[cam_id])
    camera_controller.start_receiver(cam_id, CAMERA_CONFIGS[cam_id])
    camera_controller.sync_statuses(CAMERA_CONFIGS)
    return {"status": "receiver started"}

@app.post("/api/cameras/{cam_id}/receiver/stop")
def stop_receiver(cam_id: str):
    if cam_id not in CAMERA_CONFIGS:
        raise HTTPException(status_code=404, detail="Camera not found")
         
    camera_controller.stop_receiver(cam_id, CAMERA_CONFIGS[cam_id])
    camera_controller.sync_statuses(CAMERA_CONFIGS)
    return {"status": "receiver stopped"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
