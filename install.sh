#!/usr/bin/env bash
set -euo pipefail

KIRO_DIR="${HOME}/.kiro"
MCP_DIR="${KIRO_DIR}/mcp/memory"
MCP_JSON="${KIRO_DIR}/settings/mcp.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🧠 Installing Conductor Memory MCP server..."

mkdir -p "${MCP_DIR}"

cp "${SCRIPT_DIR}/mcp/server.py" "${MCP_DIR}/server.py"
cp "${SCRIPT_DIR}/mcp/requirements.txt" "${MCP_DIR}/requirements.txt"

if [ ! -d "${MCP_DIR}/.venv" ]; then
  echo "📦 Creating virtual environment..."
  python3 -m venv "${MCP_DIR}/.venv"
fi

echo "📦 Installing dependencies..."
"${MCP_DIR}/.venv/bin/pip" install --quiet -r "${MCP_DIR}/requirements.txt"

PYTHON_PATH="${MCP_DIR}/.venv/bin/python3"
SERVER_PATH="${MCP_DIR}/server.py"

if [ -f "${MCP_JSON}" ]; then
  if grep -q '"memory"' "${MCP_JSON}"; then
    echo "⚡ Memory already registered in mcp.json — updating paths..."
  else
    echo "📝 Registering Memory in mcp.json..."
  fi
  python3 -c "
import json
with open('${MCP_JSON}') as f:
    cfg = json.load(f)
cfg.setdefault('mcpServers', {})['memory'] = {
    'command': '${PYTHON_PATH}',
    'args': ['${SERVER_PATH}'],
    'env': {}
}
with open('${MCP_JSON}', 'w') as f:
    json.dump(cfg, f, indent=2)
print('  Done.')
"
else
  echo "📝 Creating mcp.json with Memory..."
  mkdir -p "$(dirname "${MCP_JSON}")"
  python3 -c "
import json
cfg = {'mcpServers': {'memory': {
    'command': '${PYTHON_PATH}',
    'args': ['${SERVER_PATH}'],
    'env': {}
}}}
with open('${MCP_JSON}', 'w') as f:
    json.dump(cfg, f, indent=2)
print('  Created.')
"
fi

echo ""
echo "✅ Conductor Memory installed!"
echo "   Server: ${SERVER_PATH}"
echo "   Python: ${PYTHON_PATH}"
echo ""
echo "Restart Kiro CLI to load the new MCP server."
