#!/bin/bash

# Quick Environment Switcher
# Usage: ./switch-env.sh [dev|prod]

if [ $# -eq 0 ]; then
    echo "Usage: $0 [dev|prod]"
    echo ""
    echo "Current environment:"
    source config.env
    echo "ENVIRONMENT=$ENVIRONMENT"
    exit 1
fi

case $1 in
    "dev"|"development")
        echo "Switching to DEVELOPMENT environment..."
        sed -i 's/ENVIRONMENT=.*/ENVIRONMENT=development/' config.env
        ;;
    "prod"|"production")
        echo "Switching to PRODUCTION environment..."
        sed -i 's/ENVIRONMENT=.*/ENVIRONMENT=production/' config.env
        ;;
    *)
        echo "Invalid environment: $1"
        echo "Use 'dev' or 'prod'"
        exit 1
        ;;
esac

# Run configuration script
./configure.sh
