#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/alive-common-codex.sh"

read_hook_input
session_id="${HOOK_SESSION_ID:-}"
[ -n "$session_id" ] || exit 0
find_world || exit 0
entry="$WORLD_ROOT/.alive/_squirrels/$session_id.yaml"
[ -f "$entry" ] || exit 0

ALIVE_ENTRY="$entry" python3 -c '
import datetime, os, pathlib, tempfile

target = pathlib.Path(os.environ["ALIVE_ENTRY"])
now = datetime.datetime.now(datetime.timezone.utc).isoformat()
lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
seen = {"ended": False, "last_stop": False}
output = []
for line in lines:
    if line.startswith("ended:"):
        output.append(f"ended: {now}")
        seen["ended"] = True
    elif line.startswith("last_stop:"):
        output.append(f"last_stop: {now}")
        seen["last_stop"] = True
    else:
        output.append(line)
for key in ("ended", "last_stop"):
    if not seen[key]:
        output.append(f"{key}: {now}")
fd, name = tempfile.mkstemp(prefix=".stop-", dir=target.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("\n".join(output) + "\n")
    os.replace(name, target)
finally:
    pathlib.Path(name).unlink(missing_ok=True)
'
write_recovery_record "$session_id" "Stop" || true
