#!/usr/bin/env bash

ALIVE_MARKETPLACE_NAME="alive-private-alpha"
ALIVE_PLUGIN_NAME="alive"

alive_parse_args() {
  ALIVE_CODEX_BIN="${CODEX_BIN:-}"
  ALIVE_CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
  ALIVE_MARKETPLACE=""
  ALIVE_UV_BIN="${UV_BIN:-}"
  ALIVE_SKIP_MCP_SETUP=0
  ALIVE_JSON=0
  ALIVE_REMOVE_MARKETPLACE=0
  ALIVE_WORLD_ROOT="${ALIVE_WORLD_ROOT:-}"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --codex-bin) ALIVE_CODEX_BIN="$2"; shift 2 ;;
      --codex-home) ALIVE_CODEX_HOME="$2"; shift 2 ;;
      --marketplace) ALIVE_MARKETPLACE="$2"; shift 2 ;;
      --uv-bin) ALIVE_UV_BIN="$2"; shift 2 ;;
      --skip-mcp-setup) ALIVE_SKIP_MCP_SETUP=1; shift ;;
      --world) ALIVE_WORLD_ROOT="$2"; shift 2 ;;
      --json) ALIVE_JSON=1; shift ;;
      --remove-marketplace) ALIVE_REMOVE_MARKETPLACE=1; shift ;;
      *) printf 'Unknown argument: %s\n' "$1" >&2; return 64 ;;
    esac
  done
  if [ -z "$ALIVE_CODEX_BIN" ]; then
    local bundled
    for bundled in \
      "/Applications/ChatGPT.app/Contents/Resources/codex" \
      "/Applications/Codex.app/Contents/Resources/codex"; do
      if [ -x "$bundled" ]; then
        ALIVE_CODEX_BIN="$bundled"
        break
      fi
    done
  fi
  if [ -z "$ALIVE_CODEX_BIN" ]; then
    ALIVE_CODEX_BIN=$(command -v codex 2>/dev/null || true)
  fi
  if [ -z "$ALIVE_UV_BIN" ]; then
    ALIVE_UV_BIN=$(command -v uv 2>/dev/null || true)
  fi
  export CODEX_HOME="$ALIVE_CODEX_HOME"
}

alive_require_inputs() {
  [ -x "$ALIVE_CODEX_BIN" ] || {
    printf 'Codex executable not found: %s\n' "${ALIVE_CODEX_BIN:-unset}" >&2
    return 69
  }
  "$ALIVE_CODEX_BIN" --version >/dev/null 2>&1 || {
    printf 'Codex executable cannot run: %s\n' "$ALIVE_CODEX_BIN" >&2
    printf 'Install or repair Codex, or pass --codex-bin with a working binary.\n' >&2
    return 69
  }
  [ -n "$ALIVE_MARKETPLACE" ] || {
    printf 'A built marketplace path is required via --marketplace.\n' >&2
    return 64
  }
  ALIVE_MARKETPLACE=$(cd "$ALIVE_MARKETPLACE" 2>/dev/null && pwd) || {
    printf 'Marketplace directory not found: %s\n' "$ALIVE_MARKETPLACE" >&2
    return 66
  }
  [ -f "$ALIVE_MARKETPLACE/.agents/plugins/marketplace.json" ] || {
    printf 'Marketplace catalog missing under: %s\n' "$ALIVE_MARKETPLACE" >&2
    return 66
  }
  mkdir -p "$ALIVE_CODEX_HOME"
}

alive_require_single_alive_product() {
  local config="$ALIVE_CODEX_HOME/config.toml"
  [ -f "$config" ] || return 0
  local conflicts
  conflicts=$(ALIVE_CONFIG="$config" python3 -c '
import os, pathlib, tomllib
path = pathlib.Path(os.environ["ALIVE_CONFIG"])
try:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
except (OSError, tomllib.TOMLDecodeError):
    raise SystemExit(0)
plugins = data.get("plugins", {})
for name, value in sorted(plugins.items()):
    if (
        name.startswith("alive@")
        and name != "alive@alive-private-alpha"
        and isinstance(value, dict)
        and value.get("enabled") is True
    ):
        print(name)
' 2>/dev/null || true)
  [ -z "$conflicts" ] || {
    printf 'Conflicting enabled ALIVE plugin(s): %s\n' "$(printf '%s' "$conflicts" | tr '\n' ' ')" >&2
    printf 'Private alpha requires only one ALIVE product enabled in a Codex profile.\n' >&2
    printf 'Disable the other ALIVE plugin, start a new Codex task, then install again.\n' >&2
    return 65
  }
}

alive_find_plugin_root() {
  local root="$ALIVE_CODEX_HOME/plugins/cache/$ALIVE_MARKETPLACE_NAME/$ALIVE_PLUGIN_NAME"
  [ -d "$root" ] || return 1
  local candidate
  for candidate in "$root"/*; do
    if [ -f "$candidate/.codex-plugin/plugin.json" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

alive_add_marketplace() {
  local output
  if output=$("$ALIVE_CODEX_BIN" plugin marketplace add "$ALIVE_MARKETPLACE" --json 2>&1); then
    return 0
  fi
  case "$output" in
    *already*configured*|*already*exists*|*duplicate*) return 0 ;;
    *) printf '%s\n' "$output" >&2; return 1 ;;
  esac
}

alive_install_plugin() {
  local output
  if output=$("$ALIVE_CODEX_BIN" plugin add "$ALIVE_PLUGIN_NAME@$ALIVE_MARKETPLACE_NAME" --json 2>&1); then
    return 0
  fi
  case "$output" in
    *already*installed*) return 0 ;;
    *) printf '%s\n' "$output" >&2; return 1 ;;
  esac
}

alive_setup_mcp() {
  local plugin_root="$1"
  [ "$ALIVE_SKIP_MCP_SETUP" = "1" ] && return 0
  [ -x "$ALIVE_UV_BIN" ] || {
    printf 'uv is required to prepare the locked ALIVE MCP environment.\n' >&2
    return 69
  }
  "$ALIVE_UV_BIN" sync --frozen --project "$plugin_root/mcp" \
    --no-group test --no-install-project
}

alive_emit_result() {
  local status="$1" plugin_root="${2:-}" detail="${3:-}"
  if [ "$ALIVE_JSON" = "1" ]; then
    ALIVE_STATUS="$status" ALIVE_RESULT_PLUGIN_ROOT="$plugin_root" \
      ALIVE_RESULT_MARKETPLACE="$ALIVE_MARKETPLACE" ALIVE_RESULT_DETAIL="$detail" \
      ALIVE_RESULT_CODEX_HOME="$ALIVE_CODEX_HOME" python3 -c '
import json, os
print(json.dumps({
    "status": os.environ["ALIVE_STATUS"],
    "plugin": "alive",
    "version": "3.3.0-alpha.3",
    "marketplace": os.environ.get("ALIVE_RESULT_MARKETPLACE", ""),
    "plugin_root": os.environ.get("ALIVE_RESULT_PLUGIN_ROOT", ""),
    "codex_home": os.environ.get("ALIVE_RESULT_CODEX_HOME", ""),
    "detail": os.environ.get("ALIVE_RESULT_DETAIL", ""),
}, sort_keys=True))
'
  else
    printf 'ALIVE %s (%s)\n' "$status" "$plugin_root"
    [ -z "$detail" ] || printf '%s\n' "$detail"
  fi
}
