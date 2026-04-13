#!/usr/bin/env bash
# Start the Admin Panel (backend + pre-built frontend).
# Prerequisites: venv activated, docker compose up, alembic upgrade head done.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Build frontend if dist/ does not exist
if [ ! -d admin/frontend/dist ]; then
    echo "Building admin frontend..."
    (cd admin/frontend && npm install && npm run build)
fi

echo "Starting admin server on port ${ADMIN_PORT:-8001}..."
exec python3 -m admin.backend.server
