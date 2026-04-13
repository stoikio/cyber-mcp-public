#!/bin/bash
# Configure Claude Desktop to use the local Secure MCP Gateway.
# Usage : ./setup_claude_desktop.sh
#
# macOS  : ~/Library/Application Support/Claude/claude_desktop_config.json
# Linux  : ~/.config/Claude/claude_desktop_config.json
# Windows: %APPDATA%\Claude\claude_desktop_config.json

# Detect OS
case "$(uname -s)" in
    Darwin) CONFIG_DIR="$HOME/Library/Application Support/Claude" ;;
    Linux)  CONFIG_DIR="$HOME/.config/Claude" ;;
    *)      echo "OS non supporté. Créez manuellement le fichier claude_desktop_config.json."; exit 1 ;;
esac

CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"

mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_FILE" ]; then
    cp "$CONFIG_FILE" "$CONFIG_FILE.backup.$(date +%Y%m%d%H%M%S)"
    echo "Config existante sauvegardée (.backup)"
fi

cat > "$CONFIG_FILE" << 'EOF'
{
  "mcpServers": {
    "secure-mcp-gateway": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
EOF

echo "Config Claude Desktop mise à jour : $CONFIG_FILE"
echo ""
echo "Prochaines étapes :"
echo "  1. Lance le gateway :  cd '$(pwd)' && ./start_gateway.sh"
echo "  2. Redémarre Claude Desktop"
echo "  3. Le serveur MCP 'secure-mcp-gateway' devrait apparaître avec 9 outils"
