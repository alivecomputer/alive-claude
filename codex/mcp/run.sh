#!/usr/bin/env bash
set -euo pipefail

plugin_root="${PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
mcp_python="${ALIVE_MCP_PYTHON:-$plugin_root/mcp/.venv/bin/python}"

if [[ ! -x "$mcp_python" ]]; then
  printf '%s\n' "ALIVE MCP is not prepared. Run the ALIVE private-alpha installer or doctor." >&2
  exit 78
fi

export PYTHONPATH="$plugin_root/mcp/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$mcp_python" -m alive_mcp
