#!/usr/bin/env bash
set -euo pipefail

plugin_source="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$plugin_source/lib/codex-plugin.sh"
alive_parse_args "$@"
[ -x "$ALIVE_CODEX_BIN" ] || { printf 'Codex executable not found.\n' >&2; exit 69; }
plugin_root=$(alive_find_plugin_root 2>/dev/null || true)
"$ALIVE_CODEX_BIN" plugin remove "$ALIVE_PLUGIN_NAME@$ALIVE_MARKETPLACE_NAME" --json >/dev/null 2>&1 || true
if [ "$ALIVE_REMOVE_MARKETPLACE" = "1" ]; then
  "$ALIVE_CODEX_BIN" plugin marketplace remove "$ALIVE_MARKETPLACE_NAME" --json >/dev/null 2>&1 || true
fi
alive_emit_result "uninstalled" "$plugin_root" "User worlds were not touched."
