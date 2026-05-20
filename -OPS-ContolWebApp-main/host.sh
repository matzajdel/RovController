#!/bin/bash

# Legacy host.sh - redirects to new start_service.sh
# This file is kept for backward compatibility

echo "Note: host.sh is deprecated. Use start_service.sh instead."
echo "Redirecting to new startup script..."

# Get the directory where the script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"

# Call the new startup script
exec "$SCRIPT_DIR/start_service.sh" both
