#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "Building backend image..."
docker build -f backend/Dockerfile -t ops-controlwebapp-backend:latest .

echo "Building frontend image..."
docker build -f frontend/Dockerfile -t ops-controlwebapp-frontend:latest .

echo "Docker images built successfully:"
docker images | grep "ops-controlwebapp-" || true
