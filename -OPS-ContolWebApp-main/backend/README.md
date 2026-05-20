# OPS Control WebApp Backend

FastAPI backend for rover control, telemetry, science workflows, camera/vision, manipulator control, and ROS 2 integration.

## What This Backend Provides

Core runtime:

- FastAPI HTTP API
- WebSocket channel at `/ws`
- ROS 2 node lifecycle management on startup/shutdown
- Route modules for control, steering, gamepad, vision, robot view, science, GPS, satel, topics, and more

Main server defaults from `main.py`:

- Host: `0.0.0.0`
- Port: `2137`
- Docs: `http://<host>:2137/docs`

## Prerequisites

- Linux shell (`bash`)
- Python 3.10+
- `pip`
- Optional in many deployments: ROS 2 (Humble/Foxy/Galactic) with environment setup
- Optional in many deployments: GNU `screen` for related scripts/process tooling
- Optional based on hardware: camera and serial support packages

## System App Dependencies

The backend also depends on non-Python CLI tools used by SSH, vision, Bluetooth, and process management paths.

System requirements file:

- `backend/requirements-system.txt`

Key commands used by backend code:

- `ssh` (from `openssh-client`)
- `sshpass`
- `screen`
- `bluetoothctl` (from `bluez`)
- `v4l2-ctl` (from `v4l-utils`)
- `gst-launch-1.0` (from GStreamer packages)
- `pkill` and `pgrep` (from `procps`)
- `mjpg_streamer` (legacy/robot camera flows)
- `curl` (test/helper scripts)

Install example on Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y \
	openssh-client sshpass screen bluez v4l-utils \
	gstreamer1.0-tools gstreamer1.0-plugins-base \
	gstreamer1.0-plugins-good gstreamer1.0-plugins-bad \
	gstreamer1.0-plugins-ugly gstreamer1.0-libav \
	procps curl
```

`mjpg_streamer` may be package-managed (`mjpg-streamer`) or require source build, depending on distro.

Quick check after install:

```bash
command -v ssh sshpass screen bluetoothctl v4l2-ctl gst-launch-1.0 pkill pgrep curl
```

## Python Dependencies

From `backend/requirements.txt`:

- `fastapi==0.104.1`
- `uvicorn[standard]==0.24.0`
- `websockets==12.0`
- `python-socketio`
- `python-engineio==4.7.1`
- `ros-geometry_msgs`
- `ros-sensor_msgs`
- `ros-std_msgs`
- `pydantic==2.5.0`
- `python-multipart==0.0.6`
- `evdev`
- `opencv-python==4.8.1.78`
- `numpy==1.24.3`
- `cv-bridge`
- `rclpy`
- `ikpy`
- `scipy`
- `aiohttp`
- `Pillow`
- `pyserial`

Important notes:

- Some ROS-related packages (`rclpy`, `cv-bridge`, `ros-*`) are often installed via ROS distribution packages rather than plain PyPI in many environments.
- If `pip install -r requirements.txt` fails on ROS packages, install those through your ROS/OS package manager and keep Python-only packages in your venv.

## Install

From repository root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

If you are setting up a fresh machine, install system dependencies from `backend/requirements-system.txt` first.

## Start

Preferred startup (matches your request style):

```bash
cd backend
./start_backend.sh
```

What `start_backend.sh` does:

- Switches to backend directory
- Exports `PYTHONPATH`
- Sets `ROS_DOMAIN_ID=0`
- Loads variables from `backend/.env` when present
- Sources ROS 2 setup from common paths when available
- Runs `python3 main.py`

Manual startup alternative:

```bash
cd backend
source .venv/bin/activate
python3 main.py
```

## Docker

Build backend image only:

```bash
docker build -f backend/Dockerfile -t ops-controlwebapp-backend:latest .
```

Run backend container:

```bash
docker run --rm -p 2137:2137 --name ops-backend ops-controlwebapp-backend:latest
```

Compose (frontend + backend together from repo root):

```bash
docker compose up --build
```

Docker-related files:

- `backend/Dockerfile`
- `backend/requirements-docker.txt`
- `backend/requirements-system.txt`
- `docker-compose.yml`
- `build_docker_images.sh`

## How To Use

1. Start backend using `./start_backend.sh`.
2. Verify health:

```bash
curl http://localhost:2137/health
```

3. Open API docs:

```text
http://localhost:2137/docs
```

4. Start frontend separately (`frontend/`) and connect to this backend on port `2137`.

## Key Routes

Routers registered in `main.py` include:

- `health`
- `control`
- `led`
- `gamepad`
- `steering`
- `bluetooth`
- `vision` (prefix `/vision`)
- `robot_view` (prefix `/robot`)
- `screen_manager`
- `topics`
- `ui_config`
- `science_layout`
- `science`
- `ssh`
- `gps`
- `satel`
- `sequence`
- `websocket`

WebSocket endpoint:

- `WS /ws`

## Environment Variables

Common environment variables used by the backend:

- `HOST` (default `0.0.0.0`)
- `PORT` (default `2137`)
- `LOG_LEVEL` (default `info`)
- `ROS_DOMAIN_ID` (set to `0` in startup script)

You can define variables in `backend/.env`; the startup script exports them before launching.

## Troubleshooting

- Backend starts but frontend cannot connect: verify `http://<host>:2137/health` and firewall rules.
- ROS errors on startup: ensure your ROS environment is installed and sourceable.
- Import errors for ROS Python modules: install ROS-side packages (`rclpy`, `cv_bridge`, message packages) in your ROS environment.
- Camera/evdev/serial errors: verify device permissions and required system drivers/libraries.
- `sshpass not installed` errors: install `sshpass` on backend host.
- Vision auto-discovery fails with `v4l2-ctl`/`gst-launch-1.0` not found: install `v4l-utils` and GStreamer packages on the host (and on remote robot if discovery/streaming runs there).
- SSH camera/session actions fail remotely: confirm the remote robot also has `screen`, `v4l2-ctl`, `gst-launch-1.0`, and `mjpg_streamer` where needed.

## Useful Files

- `backend/main.py`
- `backend/start_backend.sh`
- `backend/requirements.txt`
- `backend/requirements-system.txt`
- `backend/requirements-docker.txt`
- `backend/Dockerfile`
- `backend/ARCHITECTURE.md`
- `backend/service_registry.py`
