#!/bin/sh
set -e

echo "=== Secure MCP Gateway — Entrypoint ==="

# Run Alembic migrations (idempotent)
echo "[1/3] Applying database migrations..."
alembic upgrade head

# Seed policies (idempotent upsert — safe to run on every deploy)
echo "[2/3] Seeding policies..."
python3 seed_policies.py

# Start the gateway (and optionally the admin panel)
echo "[3/3] Starting services..."

if [ "${ENABLE_ADMIN:-false}" = "true" ]; then
    python3 -m admin.backend.server &
    ADMIN_PID=$!
    echo "  Admin panel started (PID $ADMIN_PID) on port ${ADMIN_PORT:-8001}"
fi

exec python3 mcp_secure_gateway.py
