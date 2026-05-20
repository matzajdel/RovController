#!/bin/bash

# OPS Control WebApp - Configuration Script
# This script automatically configures URLs based on environment setting

CONFIG_FILE="config.env"
FRONTEND_JOYSTICK_FILE="frontend/src/components/VirtualJoystick.jsx"

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: $CONFIG_FILE not found!"
    exit 1
fi

# Load configuration
source "$CONFIG_FILE"

# Determine URLs based on environment
if [ "$ENVIRONMENT" = "production" ]; then
    BACKEND_URL="http://${PROD_BACKEND_IP}:${BACKEND_PORT}"
    WS_URL="ws://${PROD_BACKEND_IP}:${BACKEND_PORT}/ws"
    echo "Configuring for PRODUCTION environment"
    echo "Backend: $BACKEND_URL"
    echo "WebSocket: $WS_URL"
else
    BACKEND_URL="http://${DEV_BACKEND_IP}:${BACKEND_PORT}"
    WS_URL="ws://${DEV_BACKEND_IP}:${BACKEND_PORT}/ws"
    echo "Configuring for DEVELOPMENT environment"
    echo "Backend: $BACKEND_URL"
    echo "WebSocket: $WS_URL"
fi

# Update frontend configuration
if [ -f "$FRONTEND_JOYSTICK_FILE" ]; then
    echo "Updating frontend configuration..."
    
    # Create backup
    cp "$FRONTEND_JOYSTICK_FILE" "${FRONTEND_JOYSTICK_FILE}.backup"
    
    # Update backend URL
    sed -i "s|const BACKEND_URL = \".*\";|const BACKEND_URL = \"$BACKEND_URL\";|g" "$FRONTEND_JOYSTICK_FILE"
    
    # Update WebSocket URL
    sed -i "s|const WS_URL = \".*\";|const WS_URL = \"$WS_URL\";|g" "$FRONTEND_JOYSTICK_FILE"
    
    echo "Frontend configuration updated successfully!"
else
    echo "Warning: Frontend file not found: $FRONTEND_JOYSTICK_FILE"
fi

# Update backend environment file
echo "Updating backend configuration..."
cat > backend/.env << EOF
# Auto-generated backend configuration
# Generated on $(date)

# Server settings
HOST=$BACKEND_HOST
PORT=$BACKEND_PORT
LOG_LEVEL=$LOG_LEVEL

# ROS 2 settings
ROS_DOMAIN_ID=$ROS_DOMAIN_ID
ROS_LOCALHOST_ONLY=$ROS_LOCALHOST_ONLY

# Robot control settings
MAX_LINEAR_SPEED=$MAX_LINEAR_SPEED
MAX_ANGULAR_SPEED=$MAX_ANGULAR_SPEED
COMMAND_TIMEOUT=$COMMAND_TIMEOUT

# Environment info
ENVIRONMENT=$ENVIRONMENT
EOF

echo "Backend configuration updated successfully!"

# Update main startup script info
echo "Updating startup script messages..."
sed -i "s|Backend API: http://.*|Backend API: $BACKEND_URL|g" start_service.sh
sed -i "s|WebSocket: ws://.*|WebSocket: $WS_URL|g" start_service.sh

echo ""
echo "=== Configuration Complete ==="
echo "Environment: $ENVIRONMENT"
echo "Backend API: $BACKEND_URL"
echo "WebSocket: $WS_URL"
echo ""
echo "To change environment, edit config.env and run this script again."
