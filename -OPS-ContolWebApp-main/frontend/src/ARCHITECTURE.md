# Frontend Architecture

Quick reference for the frontend source layout.

## Root Files

| File | Purpose |
|---|---|
| `main.jsx` | React entry point, renders `<App />` |
| `App.jsx` | Router, tab navigation, layout |
| `config.js` | Backend URL configuration (`BACKEND_CONFIG`) |
| `index.css` | Global styles |

## Feature Directories

| Directory | Purpose |
|---|---|
| `VirtualJoystick/` | Main control panel — joystick, gamepad, steering modes |
| `RobotView/` | 3D robot visualization — URDF rendering, joint controls, IK |
| `Vision/` | Camera streams, object detection, camera management |
| `Science/` | Science data dashboard, topic watchers, charts |
| `GPS/` | GPS map, waypoint management, position tracking |
| `StatusJetson/` | System status, screen sessions, MicroROS logs |
| `Navbar/` | Navigation bar component |

## Shared

| Path | Purpose |
|---|---|
| `hooks/useBackendHealth.js` | Backend connectivity health check hook |
| `icons/` | SVG icon assets |

## Key Files in `VirtualJoystick/`

| File | Purpose |
|---|---|
| `Constants.js` | `BACKEND_CONFIG` re-export, shared constants |
| `VirtualJoystick.jsx` | Main control tab component |
| `VirtualJoystick.css` | Control tab styles |
| `JoystickCanvas.jsx` | Touch/mouse joystick widget |
| `GamepadPanel.jsx` | Physical gamepad device management |
| `SteeringPanel.jsx` | Steering mode selector & controls |

## Key Files in `RobotView/`

| File | Purpose |
|---|---|
| `RobotView.jsx` | Main 3D view — URDF fetch, WebSocket, scene |
| `URDFRobot.jsx` | 3D robot model with steering visualization |
| `JointControls.jsx` | Joint & wheel steering sliders |
| `IKControls.jsx` | Inverse kinematics target controls |
