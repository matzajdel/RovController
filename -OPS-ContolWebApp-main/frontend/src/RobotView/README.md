# RobotView Module

3D manipulator and rover visualization module used at route `/manipulator`.

## Scope

This module renders robot geometry and joint state in the frontend using Three.js through React Three Fiber.

Main files:

- `RobotView.jsx`
- `URDFRobot.jsx`
- `JointControls.jsx`
- `PresetButtons.jsx`
- `ViewControls.jsx`
- `hooks/`

## Dependencies

Module-specific runtime dependencies (already included in `frontend/package.json`):

- `three`
- `@react-three/fiber`
- `@react-three/drei`
- `react`
- `react-dom`

Backend-side dependencies commonly needed for manipulator features:

- Python package `ikpy`
- Python package `scipy`
- FastAPI backend running on port `2137`

## Install

From repository root:

```bash
cd frontend
npm install
```

If manipulator IK endpoints are used, install backend packages too:

```bash
cd backend
pip install ikpy scipy
```

## Start

Use the standard frontend startup script:

```bash
cd frontend
./start_frontend.sh
```

Then open:

- `http://localhost:3000/manipulator`

Alternative without script:

```bash
cd frontend
npm run dev -- --port 3000 --host 0.0.0.0
```

## How To Use

1. Ensure backend is running at `http://localhost:2137`.
2. Open `/manipulator` in the frontend.
3. Use joint sliders to send joint position updates.
4. Use preset buttons for known arm poses.
5. Use camera controls to switch/adjust the 3D view.

## Backend Endpoints Used

Typical endpoints used by RobotView:

- `GET /robot/urdf`
- `GET /robot/status`
- `POST /robot/set_joints`
- `POST /robot/ik_solve`

Also relies on WebSocket updates from backend (`/ws` on port `2137`) for real-time synchronization.

## Troubleshooting

- Blank 3D view: check browser console errors and verify frontend build completed
- No robot updates: verify backend health endpoint and WebSocket connection
- IK request errors: ensure backend has `ikpy` and `scipy` installed
- Connection works locally but not from LAN: confirm frontend starts with `--host 0.0.0.0` and firewall allows port `3000`

## See Also

- `frontend/README.md`
- `frontend/src/ARCHITECTURE.md`
- `backend/routes/robot_view.py`
