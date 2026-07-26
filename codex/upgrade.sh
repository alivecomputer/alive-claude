#!/usr/bin/env bash
set -euo pipefail

plugin_source="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$plugin_source/lib/codex-plugin.sh"
alive_parse_args "$@"
alive_require_inputs
alive_require_single_alive_product
"$ALIVE_CODEX_BIN" plugin remove "$ALIVE_PLUGIN_NAME@$ALIVE_MARKETPLACE_NAME" --json >/dev/null 2>&1 || true
"$ALIVE_CODEX_BIN" plugin marketplace remove "$ALIVE_MARKETPLACE_NAME" --json >/dev/null 2>&1 || true
alive_add_marketplace
alive_install_plugin
plugin_root=$(alive_find_plugin_root)
alive_setup_mcp "$plugin_root"
alive_emit_result "upgraded" "$plugin_root" "Review hook trust again when hook definitions change."
