#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/alive-common-codex.sh"

read_hook_input
read_session_fields
find_world || exit 0

session_id="${HOOK_SESSION_ID:-}"
safe_session=$(printf '%s' "$session_id" | tr -cd 'A-Za-z0-9._-')
plugin_data="${PLUGIN_DATA:-${CLAUDE_PLUGIN_DATA:-}}"
recovery=""
if [ -n "$plugin_data" ] && [ -n "$safe_session" ] && [ -f "$plugin_data/recovery/$safe_session.json" ]; then
  recovery="$plugin_data/recovery/$safe_session.json"
fi
entry="$WORLD_ROOT/.alive/_squirrels/$session_id.yaml"

context=$(ALIVE_RECOVERY_FILE="$recovery" ALIVE_ENTRY="$entry" \
  ALIVE_WORLD="$WORLD_ROOT" ALIVE_SESSION="$session_id" python3 -c '
import json, os, pathlib

world = os.environ["ALIVE_WORLD"]
session = os.environ.get("ALIVE_SESSION", "")
payload = {}
recovery = pathlib.Path(os.environ["ALIVE_RECOVERY_FILE"]) if os.environ.get("ALIVE_RECOVERY_FILE") else None
if recovery and recovery.is_file():
    try:
        payload = json.loads(recovery.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
if not payload:
    entry = pathlib.Path(os.environ["ALIVE_ENTRY"])
    if entry.is_file():
        for line in entry.read_text(encoding="utf-8", errors="replace").splitlines():
            if ":" not in line or line[:1].isspace():
                continue
            key, value = line.split(":", 1)
            value = value.strip()
            if value.startswith("\""):
                try: value = json.loads(value)
                except json.JSONDecodeError: pass
            payload[key.strip()] = "" if value in {"null", "~"} else value
walnut = payload.get("walnut") or "none"
state = payload.get("recovery_state") or "No saved recovery state."
saves = payload.get("saves", 0)
print(
    f"ALIVE v3.3 resumed orientation.\nWorld: {world}\nWalnut: {walnut}\n"
    f"Completed saves: {saves}\nRecovery state: {state}\nSession: {session}\n"
    "Re-read the walnut kernel before relying on it. Explicit alive-save remains the guaranteed persistence path."
)
')
orientation=$(read_bounded_orientation)
context=$(compose_bounded_orientation_context "$context" "$orientation")
emit_additional_context "SessionStart" "$context"
