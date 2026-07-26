#!/usr/bin/env bash
set -euo pipefail

plugin_source="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$plugin_source/lib/codex-plugin.sh"
alive_parse_args "$@"
alive_require_inputs
alive_require_single_alive_product
alive_add_marketplace
alive_install_plugin
plugin_root=$(alive_find_plugin_root)
alive_setup_mcp "$plugin_root"
alive_emit_result "installed" "$plugin_root" "Native plugin hooks require review and trust inside Codex."
