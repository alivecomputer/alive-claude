#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/alive-common-codex.sh"

read_hook_input
read_session_fields

if ! find_world; then
  context="ALIVE v3.3 is installed, but no ALIVE world was found from this working directory. No walnut is loaded. Use the alive-world skill to create or locate a world; do not infer private context."
  emit_additional_context "SessionStart" "$context"
  exit 0
fi

session_id="${HOOK_SESSION_ID:-}"
if [ -z "$session_id" ]; then
  session_id=$(python3 -c 'import uuid; print(uuid.uuid4().hex[:12])')
fi

squirrels_dir="$WORLD_ROOT/.alive/_squirrels"
mkdir -p "$squirrels_dir"
entry="$squirrels_dir/$session_id.yaml"
if [ -f "$entry" ]; then
  write_recovery_record "$session_id" "SessionStart" || true
  printf '%s' "$HOOK_INPUT" | bash "$script_dir/alive-session-resume.sh"
  exit 0
fi

ALIVE_ENTRY="$entry" ALIVE_SESSION_ID="$session_id" \
  ALIVE_MODEL="${HOOK_MODEL:-unknown}" ALIVE_TRANSCRIPT="${HOOK_TRANSCRIPT:-}" \
  ALIVE_CWD="${HOOK_CWD:-$PWD}" python3 -c '
import datetime, json, os, pathlib, tempfile

target = pathlib.Path(os.environ["ALIVE_ENTRY"])
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
q = json.dumps
session = os.environ["ALIVE_SESSION_ID"]
model = os.environ.get("ALIVE_MODEL", "unknown")
transcript = os.environ.get("ALIVE_TRANSCRIPT", "")
cwd = os.environ.get("ALIVE_CWD", "")
text = "\n".join([
    f"session_id: {q(session)}",
    "runtime_id: squirrel.core@3.3",
    f"engine: {q(model)}",
    "walnut: null",
    "topic: null",
    f"started: {q(now)}",
    "ended: null",
    "saves: 0",
    "last_saved: null",
    f"transcript: {q(transcript)}",
    f"cwd: {q(cwd)}",
    "recovery_state: \"Session started; no walnut loaded.\"",
    "stash: []",
    "actions: []",
    "working: []",
    "",
])
fd, name = tempfile.mkstemp(prefix=".session-", dir=target.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    os.replace(name, target)
finally:
    pathlib.Path(name).unlink(missing_ok=True)
'

write_recovery_record "$session_id" "SessionStart" || true
context="ALIVE v3.3 found world: $WORLD_ROOT
No walnut has been loaded automatically. Use the alive-load-context skill before claiming walnut context. Explicit alive-save is the guaranteed persistence path; lifecycle hooks are best-effort assistance. Session: $session_id."
orientation=$(read_bounded_orientation)
context=$(compose_bounded_orientation_context "$context" "$orientation")
emit_additional_context "SessionStart" "$context"
