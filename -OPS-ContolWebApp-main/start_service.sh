#!/bin/bash

# OPS Control WebApp - Unified Startup Script
# This script starts backend (Python), GPS Service, and frontend (React) services

echo "Starting OPS Control WebApp..."

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PROJECT_DIR="$SCRIPT_DIR"

# Check if we're running both services or just one
MODE=${1:-"both"}

# Global PIDs
BACKEND_PID=""
GPS_PID=""
FRONTEND_PID=""

# Function to start backend
start_backend() {
    echo "Setting up Python Environment..."
    cd "$PROJECT_DIR/backend"
    
    # Check if virtual environment exists, create if not
    if [ ! -d "venv" ]; then
        echo "Creating Python virtual environment..."
        python3 -m venv venv
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Set environment variables
    export PYTHONPATH="${PYTHONPATH}:${PROJECT_DIR}/backend"
    export ROS_DOMAIN_ID=0
    
    # Source ROS 2 setup if available
    if [ -f "/opt/ros/humble/setup.bash" ]; then
        echo "Sourcing ROS 2 Humble..."
        source /opt/ros/humble/setup.bash
    elif [ -f "/opt/ros/foxy/setup.bash" ]; then
        echo "Sourcing ROS 2 Foxy..."
        source /opt/ros/foxy/setup.bash
    fi
    
    # --- 1. Start Main Backend ---
    echo "Starting FastAPI Main Backend (Port 8000)..."
    python3 main.py &
    BACKEND_PID=$!
    echo "Backend started with PID: $BACKEND_PID"

    # --- 2. Start GPS Service ---
    echo "Starting GPS Service (Port 5001)..."
    python3 gps_service.py &
    GPS_PID=$!
    echo "GPS Service started with PID: $GPS_PID"
}

# Function to start frontend
start_frontend() {
    echo "Starting React Frontend..."
    cd "$PROJECT_DIR/frontend"
    
    export NVM_DIR="$HOME/.nvm"
    # Źródłuj NVM jeśli istnieje
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    nvm use 18

    echo "Node.js version: $(node -v)"
    echo "npm version: $(npm -v)"
    
    # Start the development server
    echo "Starting React frontend on port 3000..."
    npm run dev -- --port 3000 --host
    FRONTEND_PID=$!
    echo "Frontend started with PID: $FRONTEND_PID"
}

# Function to handle cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    
    if [ ! -z "$GPS_PID" ]; then
        kill $GPS_PID 2>/dev/null
        echo "GPS Service stopped"
    fi
    
    if [ ! -z "$BACKEND_PID" ]; then
        kill $BACKEND_PID 2>/dev/null
        echo "Backend stopped"
    fi
    
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null
        echo "Frontend stopped"
    fi
    
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

# Start services based on mode
case $MODE in
    "backend")
        start_backend
        # Wait for both python processes
        wait $BACKEND_PID $GPS_PID
        ;;
    "frontend")
        start_frontend
        wait $FRONTEND_PID
        ;;
    "both"|*)
        start_backend
        sleep 3  # Give backends time to start
        start_frontend
        
        echo ""
        echo "=== OPS Control WebApp Started ==="
        echo "Backend API:  http://localhost:8000"
        echo "GPS API:      http://localhost:5001"
        echo "Frontend UI:  http://localhost:3000"
        echo ""
        echo "Press Ctrl+C to stop all services"
        
        # Wait for all background processes
        wait
        ;;
esac