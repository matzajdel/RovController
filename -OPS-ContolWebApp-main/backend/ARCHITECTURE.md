# Backend Architecture

Quick reference for the backend file layout.

## Root Files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app, CORS, lifespan, router registration |
| `models.py` | Pydantic request/response models |
| `service_registry.py` | Singleton instances of all services |
| `requirements.txt` | Python dependencies |
| `start_backend.sh` | Launch script |
| `mock_joint_publisher.py` | Dev tool — fake joint state publisher |

## `services/` — Business Logic

| File | Purpose |
|---|---|
| `ros_node.py` | ROS 2 node, publishers, subscribers, WebSocket broadcast |
| `gamepad_manager.py` | HID gamepad scanning, event loop, evdev bridge |
| `legacy_steering.py` | Original joystick-style control processing |
| `new_steering.py` | TYPE_1/2/3 steering mode processing |
| `advanced_steering.py` | PROSTY/SKRĘT/OBRÓT/FREESTYLE steering |
| `screen_manager.py` | GNU Screen session management, script XML |
| `gps_tracker.py` | Standalone GPS Flask microservice (port 5001) |
| `bluetooth_manager.py` | Bluetooth device scanning & pairing |

## `routes/` — API Endpoints

| File | Prefix | Purpose |
|---|---|---|
| `health.py` | `/` | Health check, status |
| `control.py` | `/` | cmd_vel, joystick, manipulator control |
| `gamepad.py` | `/` | Gamepad device management, HID events |
| `steering.py` | `/` | Advanced steering modes |
| `robot_view.py` | `/robot` | URDF, joint control, IK, WebSocket |
| `vision.py` | `/` | Camera streams & detection |
| `topics.py` | `/` | ROS 2 topic pub/sub, saved commands |
| `screen_manager.py` | `/ros2` | Screen session CRUD |
| `science.py` | `/` | Science data watchers |
| `science_layout.py` | `/` | Science dashboard layout persistence |
| `gps.py` | `/` | GPS waypoint publishing |
| `led.py` | `/` | LED & RGB control |
| `bluetooth.py` | `/` | Bluetooth scan/pair |
| `ssh.py` | `/` | SSH tunnel management |
| `ui_config.py` | `/` | UI config persistence |
| `websocket.py` | `/` | General WebSocket endpoint |

## `config/` — Static Configuration

| File | Purpose |
|---|---|
| `camera_config.py` | Camera stream URL/pipeline definitions |
| `remote_cameras.json` | Remote camera endpoint registry |
| `ros2_control_example.yaml` | Example ROS 2 control config |

## `data/` — Runtime Persistence

| File | Purpose |
|---|---|
| `gamepad_config.txt` | Gamepad axis mapping & deadzone |
| `gps_config.json` | GPS service settings |
| `last_position.json` | Last known rover GPS position |
| `saved_commands.json` | Saved ROS 2 topic commands |
| `saved_ui_config.json` | UI layout configuration |
| `science_config.xml` | Science watcher definitions & buffer |
| `science_layout.json` | Science dashboard layout |
| `jetson_scripts.xml` | Screen session script definitions |

## `urdf/`

| File | Purpose |
|---|---|
| `mars_rover.urdf` | Robot URDF with crab-drive steering |
