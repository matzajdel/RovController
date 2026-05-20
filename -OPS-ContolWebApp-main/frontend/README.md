# OPS Control WebApp Frontend

React + Vite frontend for rover operations: driving, vision, robot view, science, GPS, satel telemetry, and system status.

## What This Frontend Connects To

The app builds backend URLs dynamically from the browser hostname (see `src/config.js`):

- FastAPI backend: `http://<host>:2137`
- Main WebSocket: `ws://<host>:2137/ws`
- GPS backend: `http://<host>:5001`
- ROS bridge WebSocket: `ws://<host>:9090`

Main routes in the UI:

- `/` joystick and steering
- `/wizja` vision
- `/manipulator` robot 3D view
- `/science` science panel
- `/status-jetson` status and logs
- `/gps` map and GPS
- `/satel` satel view

## Prerequisites

- Linux shell (`bash`)
- Node.js 18.x
- npm 9+ (or compatible with Node 18)
- Python backend running on port `2137`
- Optional ROS/gamepad support needs ROS 2 with `rosbridge_server`

Notes about `./start_frontend.sh`:

- Script starts Vite on port `3000` and host `0.0.0.0`
- Script also starts `rosbridge_websocket` as a child subprocess and stops it when frontend exits
- Script currently prepends a hardcoded Node path: `/home/legendary/.nvm/versions/node/v18.20.8/bin`

If your machine uses a different Node install location, update that line in `start_frontend.sh`.

## Dependencies

Production dependencies (`frontend/package.json`):

- `react` `^18.2.0`
- `react-dom` `^18.2.0`
- `react-router-dom` `^6.20.0`
- `nipplejs` `^0.9.0`
- `leaflet` `^1.9.4`
- `react-leaflet` `^4.2.1`
- `three` `^0.160.1`
- `@react-three/fiber` `^8.18.0`
- `@react-three/drei` `^9.122.0`

Dev dependencies:

- `vite` `^4.5.14`
- `@vitejs/plugin-react` `^4.0.0`

## Install

From repository root:

```bash
cd frontend
npm install
```

## Start

Preferred startup (matches your request):

```bash
cd frontend
./start_frontend.sh
```

Expected result:

- Vite dev server on `http://<host>:3000`
- rosbridge WebSocket on `ws://<host>:9090` (if ROS tools are available)

Alternative startup without script:

```bash
cd frontend
npm run dev -- --port 3000 --host 0.0.0.0
```

## How To Use

1. Start backend services first (at minimum FastAPI on `:2137`).
2. Start frontend with `./start_frontend.sh`.
3. Open `http://localhost:3000` (or `http://<your-ip>:3000` from another device).
4. Use the navigation bar to open each module (`/`, `/wizja`, `/manipulator`, `/science`, `/status-jetson`, `/gps`, `/satel`).
5. Verify connection status in the UI before sending robot commands.

## Build And Preview

```bash
cd frontend
npm run build
npm run preview
```

`npm run preview` uses Vite preview default settings.
`npm run serve` is also available and serves preview on port `3000`.

## Docker

Build frontend image only:

```bash
docker build -f frontend/Dockerfile -t ops-controlwebapp-frontend:latest .
```

Run frontend container:

```bash
docker run --rm -p 3000:3000 --name ops-frontend ops-controlwebapp-frontend:latest
```

Compose (frontend + backend together from repo root):

```bash
docker compose up --build
```

Docker-related files:

- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `docker-compose.yml`
- `build_docker_images.sh`

## Troubleshooting

- `node: command not found`: install Node 18, or fix the Node path in `start_frontend.sh`
- `screen: command not found`: install `screen` or start frontend with plain `npm run dev`
- ROS bridge does not start: ensure `ROS_DISTRO` is set and `rosbridge_server` is installed
- Frontend cannot reach backend: verify backend is running at `http://<host>:2137/health`
- Access from another machine fails: ensure firewall allows port `3000`

## Relevant Files

- `frontend/start_frontend.sh`
- `frontend/package.json`
- `frontend/src/config.js`
- `frontend/src/App.jsx`
- `frontend/src/ARCHITECTURE.md`
