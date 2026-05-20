#!/bin/bash
# Add Remote HTTP/MJPEG Camera to Backend
# This allows backend to connect to remote MJPEG streams (no ROS2)

set -e

echo "=========================================="
echo "  Add Remote HTTP Camera to Backend"
echo "=========================================="
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"

# Get camera configuration
echo "Enter remote camera details:"
echo ""

read -p "Camera name/ID (e.g., front_cam, camera1): " CAMERA_ID
if [ -z "$CAMERA_ID" ]; then
    echo "Error: Camera ID required"
    exit 1
fi

read -p "Camera MJPEG stream URL: " STREAM_URL
if [ -z "$STREAM_URL" ]; then
    echo "Error: Stream URL required"
    echo "Example: http://192.168.1.100:8080/?action=stream"
    exit 1
fi

read -p "Camera friendly name [default: Remote $CAMERA_ID]: " CAMERA_NAME
CAMERA_NAME="${CAMERA_NAME:-Remote $CAMERA_ID}"

echo ""
echo "Configuration:"
echo "  ID: $CAMERA_ID"
echo "  Name: $CAMERA_NAME"
echo "  URL: $STREAM_URL"
echo ""

# Create camera config file
mkdir -p "$BACKEND_DIR/config"

CONFIG_FILE="$BACKEND_DIR/config/remote_cameras.json"

# Check if file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "{\"cameras\": []}" > "$CONFIG_FILE"
    echo "✓ Created camera config file"
fi

# Add camera to config using Python
python3 << EOF
import json

config_file = "$CONFIG_FILE"

# Load existing config
with open(config_file, 'r') as f:
    config = json.load(f)

# Add new camera
new_camera = {
    "id": "http:$CAMERA_ID",
    "name": "$CAMERA_NAME",
    "url": "$STREAM_URL",
    "type": "http_mjpeg",
    "enabled": True
}

# Check if camera already exists
existing_ids = [cam.get('id') for cam in config['cameras']]
if new_camera['id'] in existing_ids:
    # Update existing
    for i, cam in enumerate(config['cameras']):
        if cam.get('id') == new_camera['id']:
            config['cameras'][i] = new_camera
            print(f"✓ Updated existing camera: {new_camera['id']}")
            break
else:
    # Add new
    config['cameras'].append(new_camera)
    print(f"✓ Added new camera: {new_camera['id']}")

# Save config
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

print(f"✓ Saved to {config_file}")
EOF

echo ""
echo "=========================================="
echo "✓ Camera Added!"
echo "=========================================="
echo ""
echo "Current cameras in config:"
python3 -c "import json; print('\n'.join([f\"  - {c['id']}: {c['name']} ({c['url']})\" for c in json.load(open('$CONFIG_FILE'))['cameras']]))"

echo ""
echo "Next steps:"
echo "1. Restart backend to load new camera"
echo "2. Open Vision tab in web UI"
echo "3. Camera will appear as: $CAMERA_NAME"
echo ""

# Offer to test connection
read -p "Test camera connection now? (y/N): " test_now
if [ "$test_now" = "y" ] || [ "$test_now" = "Y" ]; then
    echo ""
    echo "Testing connection to $STREAM_URL..."
    
    if command -v curl &> /dev/null; then
        if curl -s --max-time 5 "$STREAM_URL" > /dev/null 2>&1; then
            echo "✓ Camera stream is accessible"
        else
            echo "✗ Could not connect to camera stream"
            echo "Check:"
            echo "  - Is mjpg-streamer running on remote host?"
            echo "  - Is the URL correct?"
            echo "  - Can you ping the remote host?"
        fi
    else
        echo "curl not found, skipping test"
    fi
fi

echo ""
echo "To remove this camera later:"
echo "  Edit: $CONFIG_FILE"
echo ""
