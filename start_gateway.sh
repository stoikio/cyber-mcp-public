#!/bin/bash
# Secure MCP Gateway — Script de lancement local
# Usage : ./start_gateway.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Vérifier Python 3
if ! command -v python3 &> /dev/null; then
    echo "Erreur : python3 non trouvé. Installez Python 3.11+ via brew install python3"
    exit 1
fi

# Vérifier les dépendances
python3 -c "import mcp" 2>/dev/null || {
    echo "Installation des dépendances..."
    pip3 install mcp uvicorn starlette httpx --break-system-packages 2>/dev/null || \
    pip3 install mcp uvicorn starlette httpx
}

echo "=== Secure MCP Gateway ==="
echo "Démarrage sur http://localhost:8000/mcp"
echo "Arrêter avec Ctrl+C"
echo ""

# Variables d'environnement
export HOST="${HOST:-0.0.0.0}"
export PORT="${PORT:-8000}"
export GMAIL_MODE="${GMAIL_MODE:-mock}"
export ENV="${ENV:-dev}"

python3 mcp_secure_gateway.py
