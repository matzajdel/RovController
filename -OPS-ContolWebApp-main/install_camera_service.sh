#!/bin/bash
# Install systemd service for auto-starting robot cameras on boot

set -e

echo "=========================================="
echo "  Camera Auto-Start Service Installer"
echo "=========================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVICE_NAME="robot-cameras"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "Creating systemd service..."

sudo tee "${SERVICE_FILE}" > /dev/null << EOF
[Unit]
Description=Robot Camera HTTP Streams
After=network.target

[Service]
Type=forking
User=${USER}
WorkingDirectory=${SCRIPT_DIR}
ExecStart=${SCRIPT_DIR}/start_all_robot_cameras.sh
ExecStop=/usr/bin/pkill -f mjpg_streamer
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo "✓ Service file created: ${SERVICE_FILE}"
echo ""

echo "Enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}.service

echo "✓ Service enabled"
echo ""

echo "Starting service..."
sudo systemctl start ${SERVICE_NAME}.service

echo ""
echo "=========================================="
echo "Service installed successfully!"
echo "=========================================="
echo ""

echo "Service commands:"
echo "  sudo systemctl status ${SERVICE_NAME}   # Check status"
echo "  sudo systemctl start ${SERVICE_NAME}    # Start cameras"
echo "  sudo systemctl stop ${SERVICE_NAME}     # Stop cameras"
echo "  sudo systemctl restart ${SERVICE_NAME}  # Restart cameras"
echo "  sudo systemctl disable ${SERVICE_NAME}  # Disable auto-start"
echo ""

echo "Checking status..."
sudo systemctl status ${SERVICE_NAME} --no-pager || true
echo ""
