# OPS Control WebApp

## Overview
A modern web-based control interface for robotics applications with ROS 2 integration. The application is split into separate **backend** (Python FastAPI + ROS 2) and **frontend** (React) services for better architecture and scalability.

## Architecture

### Backend (Python)
- **FastAPI** web framework for high-performance API
- **ROS 2** integration using rclpy for direct robot communication
- **WebSocket** support for real-time bidirectional communication
- **REST API** endpoints for reliable command transmission

### Frontend (React)
- **React 18** with modern hooks-based architecture
- **Virtual Joystick** using nipplejs for intuitive control
- **WebSocket client** for real-time communication
- **Status dashboard** with connection monitoring

## Quick Start

### Prerequisites
- **Python 3.8+** with pip
- **Node.js 16+** with npm
- **ROS 2** (Humble/Foxy/Galactic) - optional but recommended
- **rosbridge-suite** - required for frontend-only steering (gamepad → `/cmd_vel`)
- Modern web browser with WebSocket support

### Install rosbridge

```bash
sudo apt install ros-${ROS_DISTRO}-rosbridge-suite
```

Rosbridge is launched automatically by `start_frontend.sh` as a frontend subprocess. It runs on port **9090** and is terminated together with the frontend process.

### Installation & Running

1. **Clone and navigate to project:**
   ```bash
   cd /path/to/OPS-ContolWebApp
   ```

2. **Configure environment (choose development or production):**
   ```bash
   # For development (localhost)
   ./switch-env.sh dev
   
   # For production (192.168.2.100:2137)
   ./switch-env.sh prod
   ```

3. **Start both services:**
   ```bash
   ./start_service.sh both
   ```

4. **Access the application:**
   - Frontend UI: http://localhost:3000 (always)
   - Backend API: depends on environment (see config)
   - API Documentation: {BACKEND_URL}/docs

### Individual Service Control

**Backend only:**
```bash
./start_service.sh backend
# or
cd backend && ./start_backend.sh
```

**Frontend only:**
```bash
./start_service.sh frontend  
# or
cd frontend && ./start_frontend.sh
```

## Usage

1. **Open the web interface** at http://localhost:3000
2. **Check connection status** - should show "Backend: connected"
3. **Enable Joystick mode** by clicking the "Joystick" button
4. **Control the robot** using the virtual joystick:
   - Forward/Backward: Y-axis movement
   - Left/Right rotation: X-axis movement
5. **Adjust speed** using the slider (0.0 to 2.0)
6. **Emergency Stop** button for immediate safety halt

## API Endpoints

### REST API
- `GET /` - Service information
- `GET /health` - Health check with ROS status
- `GET /status` - Robot connection status  
- `POST /joystick` - Send joystick command
- `POST /cmd_vel` - Send velocity command
- `POST /stop` - Emergency stop

### WebSocket
- `WS /ws` - Real-time bidirectional communication

## ROS 2 Topics

### Published by Backend
- `/cmd_vel_nav` (geometry_msgs/Twist) - Velocity commands for navigation
- `/gps_waypoint` (std_msgs/Float64MultiArray) - GPS destination coordinates [lon, lat]
- `/array_topic` (std_msgs/Float32MultiArray) - Button array commands
- `/ESP32_GIZ/led_state_topic` (std_msgs/Int32MultiArray) - LED state control
- `/joy` (sensor_msgs/Joy) - Joystick data
- `gamepad_input` (sensor_msgs/Joy) - Gamepad input data

### Subscribed by Backend  
- `/robot_feedback` (std_msgs/String) - Robot feedback
- `/battery_status` (std_msgs/String) - Battery level

## System Service Installation

To run as a system service:

1. **Copy service file:**
   ```bash
   sudo cp ops-controlwebapp.service /etc/systemd/system/
   ```

2. **Enable and start:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable ops-controlwebapp.service
   sudo systemctl start ops-controlwebapp.service
   ```

3. **Check status:**
   ```bash
   sudo systemctl status ops-controlwebapp.service
   ```

## Configuration

The application uses a centralized configuration system for easy environment switching.

### Quick Environment Switch

```bash
# Switch to development (localhost)
./switch-env.sh dev

# Switch to production (192.168.2.100:2137)  
./switch-env.sh prod

# Check current environment
./switch-env.sh
```

### Manual Configuration

Edit `config.env` to customize settings:

```bash
# Environment: "development" or "production"
ENVIRONMENT=development

# Backend Configuration
BACKEND_HOST=0.0.0.0
BACKEND_PORT=2137

# Development URLs (localhost)
DEV_BACKEND_IP=localhost
DEV_FRONTEND_IP=localhost

# Production URLs (actual deployment)
PROD_BACKEND_IP=192.168.2.100
PROD_FRONTEND_IP=192.168.2.100
```

After editing `config.env`, run:
```bash
./configure.sh
```

## Development

### Project Structure
```
-OPS-ContolWebApp/
├── backend/                 # Python FastAPI backend
│   ├── main.py             # Main FastAPI application
│   ├── requirements.txt    # Python dependencies
│   ├── start_backend.sh    # Backend startup script
│   └── README.md           # Backend documentation
├── frontend/               # React frontend
│   ├── src/
│   │   ├── App.jsx        # Main React component
│   │   └── components/
│   │       └── VirtualJoystick.jsx  # Joystick component
│   ├── package.json       # Node.js dependencies
│   ├── start_frontend.sh  # Frontend startup script
│   └── README.md          # Frontend documentation
├── start_service.sh       # Unified startup script
├── ops-controlwebapp.service  # Systemd service file
└── README.md             # This file
```

### Adding Features

1. **Backend**: Add new endpoints in `backend/main.py`
2. **Frontend**: Add new components in `frontend/src/components/`
3. **ROS Integration**: Modify the ROSNode class in `backend/main.py`

## Troubleshooting

### Common Issues

**Backend not starting:**
- Check Python dependencies: `cd backend && pip install -r requirements.txt`
- Verify ROS 2 installation: `ros2 --version`
- Check port availability: `netstat -tulpn | grep 2137`

**Frontend not starting:**
- Check Node.js dependencies: `cd frontend && npm install`
- Verify Node.js version: `node --version` (should be 16+)
- Check port availability: `netstat -tulpn | grep 3000`

**WebSocket connection issues:**
- Ensure backend is running first
- Check firewall settings for ports 2137 and 3000
- Verify browser WebSocket support

**ROS 2 integration issues:**
- Source ROS 2 setup: `source /opt/ros/humble/setup.bash`
- Check ROS_DOMAIN_ID environment variable
- Verify topic names match your robot configuration

### Logs

**System service logs:**
```bash
journalctl -u ops-controlwebapp.service -f
```

**Manual execution logs:**
Check terminal output when running services manually.

## License
MIT License

## Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request
