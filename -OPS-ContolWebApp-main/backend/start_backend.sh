#!/bin/bash

# OPS Control WebApp Backend Startup Script
# This script sets up the Python environment and starts the FastAPI server

echo "Starting OPS Control WebApp Backend..."

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
BACKEND_DIR="$SCRIPT_DIR"

# Change to backend directory
cd "$BACKEND_DIR"

# Try to create virtual environment, but continue without it if it fails
echo "Attempting to create Python virtual environment..."
#if python3 -m venv venv 2>/dev/null; then
#    echo "Virtual environment created successfully."
#    echo "Activating virtual environment..."
#    source venv/bin/activate
#    PYTHON_CMD="python"
#    PIP_CMD="pip"
#    USE_VENV=true
#else
#    echo "Virtual environment creation failed. This might be due to missing python3-venv package."
#    echo "Continuing with system Python installation..."
#    PYTHON_CMD="python3"
#    PIP_CMD="pip3"
#    USE_VENV=false
#fi

# Install/upgrade dependencies
#echo "Installing dependencies..."
#$PIP_CMD install -r requirements.txt --user

# Set environment variables
export PYTHONPATH="${PYTHONPATH}:${BACKEND_DIR}"
export ROS_DOMAIN_ID=0

# Load configuration from .env file if it exists
if [ -f ".env" ]; then
    echo "Loading configuration from .env file..."
    export $(grep -v '^#' .env | xargs)
fi

# Source ROS 2 setup if available
if [ -f "$HOME/ros2_humble/install/local_setup.bash" ]; then
    echo "Sourcing ROS 2 Humble from home directory..."
    source $HOME/ros2_humble/install/local_setup.bash
elif [ -f "/opt/ros/humble/setup.bash" ]; then
    echo "Sourcing ROS 2 Humble..."
    source /opt/ros/humble/setup.bash
elif [ -f "/opt/ros/foxy/setup.bash" ]; then
    echo "Sourcing ROS 2 Foxy..."
    source /opt/ros/foxy/setup.bash
elif [ -f "/opt/ros/galactic/setup.bash" ]; then
    echo "Sourcing ROS 2 Galactic..."
    source /opt/ros/galactic/setup.bash
else
    echo "Warning: ROS 2 not found in standard locations"
fi

# Start the FastAPI server
echo "Starting FastAPI server on port 2137..."
export PYTHON_CMD=python3
$PYTHON_CMD main.py

