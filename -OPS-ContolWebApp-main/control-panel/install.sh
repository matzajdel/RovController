#!/bin/bash
# Install OPS Control Panel as a systemd service

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_FILE="$SCRIPT_DIR/ops-control-panel.service"
DEST="/etc/systemd/system/ops-control-panel.service"

echo "Installing OPS Control Panel service..."

# Update paths in service file to match current location
sed "s|ExecStart=.*|ExecStart=/usr/bin/python3 ${SCRIPT_DIR}/server.py|" "$SERVICE_FILE" | \
sed "s|WorkingDirectory=.*|WorkingDirectory=${SCRIPT_DIR}|" | \
sudo tee "$DEST" > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable ops-control-panel.service
sudo systemctl start ops-control-panel.service

echo ""
echo "Done! Service installed and started."
echo "  Status:  sudo systemctl status ops-control-panel"
echo "  Logs:    sudo journalctl -u ops-control-panel -f"
echo "  URL:     http://localhost:1337"
