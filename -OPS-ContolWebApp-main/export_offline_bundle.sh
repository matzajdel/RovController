#!/usr/bin/env bash
set -euo pipefail

# Builds images, exports them, and creates a self-contained bundle for offline deployment.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUNDLE_DIR="$ROOT_DIR/offline-bundle"
IMAGES_TAR="$BUNDLE_DIR/images.tar"

cd "$ROOT_DIR"

echo "[1/5] Building images from docker-compose.yml..."
docker compose build

echo "[2/5] Preparing bundle directory..."
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR"

echo "[3/5] Saving Docker images..."
docker save -o "$IMAGES_TAR" \
  ops-controlwebapp-backend:latest \
  ops-controlwebapp-frontend:latest

echo "[4/5] Copying compose file and runtime data..."
cp docker-compose.yml "$BUNDLE_DIR/docker-compose.yml"
mkdir -p "$BUNDLE_DIR/backend/data" "$BUNDLE_DIR/backend/logs"
cp -a backend/data/. "$BUNDLE_DIR/backend/data/" 2>/dev/null || true
cp -a backend/logs/. "$BUNDLE_DIR/backend/logs/" 2>/dev/null || true

cat > "$BUNDLE_DIR/run_offline.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

# Loads prebuilt images and starts the full stack without rebuilding.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

docker load -i images.tar
docker compose up -d --no-build

echo
echo "Stack started."
echo "Backend:   http://localhost:2137"
echo "Frontend:  http://localhost:3000"
echo "Rosbridge: ws://localhost:9090"
echo "GPS:       http://localhost:5001"
EOF
chmod +x "$BUNDLE_DIR/run_offline.sh"

echo "[5/5] Creating archive..."
tar -C "$ROOT_DIR" -czf "$ROOT_DIR/offline-bundle.tar.gz" offline-bundle

echo
echo "Done."
echo "Created: $ROOT_DIR/offline-bundle.tar.gz"
echo "Transfer this file and run on target machine:"
echo "  tar -xzf offline-bundle.tar.gz && ./offline-bundle/run_offline.sh"
