#!/bin/bash
# Hook: Background Results Surface -- UserPromptSubmit
# ONE job only: surface completed background results as stash blocks.
# Dispatching is handled by /alive:boot-sequence, NOT this hook.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/alive-common-codex.sh"

read_hook_input
find_world || exit 0

SESSION_ID="${HOOK_SESSION_ID}"
[ -z "$SESSION_ID" ] && exit 0

BG_DIR="$WORLD_ROOT/.alive/_background"
RESULTS_FILE="$BG_DIR/results.json"

# Exit early if no results file
[ ! -f "$RESULTS_FILE" ] && exit 0

# Need python3 for JSON
[ "$ALIVE_JSON_RT" != "python3" ] && exit 0

OUTPUT=$(RESULTS_FILE="$RESULTS_FILE" python3 << 'PYEOF'
import json, sys, os

results_file = os.environ.get("RESULTS_FILE", "")
if not results_file or not os.path.isfile(results_file):
    sys.exit(0)

try:
    with open(results_file) as f:
        results_data = json.load(f)
except (json.JSONDecodeError, IOError):
    sys.exit(0)

# Handle both formats: {"results": [...]} (canonical) or bare [...] (legacy)
if isinstance(results_data, list):
    all_results = []
    for item in results_data:
        if isinstance(item, dict) and "results" in item:
            all_results.extend(item["results"])
        elif isinstance(item, dict):
            all_results.append(item)
    results_data = {"results": all_results}
elif not isinstance(results_data, dict):
    sys.exit(0)

unsurfaced = [r for r in results_data.get("results", []) if not r.get("surfaced", False)]
if not unsurfaced:
    sys.exit(0)

lines = []
for r in unsurfaced:
    lines.append(f"[{r.get('cron', '?')}] {r.get('summary', 'completed')}")
    for a in r.get("actions", []):
        if isinstance(a, dict):
            lines.append(f"  -> {a.get('label', '?')}")
        elif isinstance(a, str):
            lines.append(f"  -> {a}")
    r["surfaced"] = True

try:
    with open(results_file, "w") as f:
        json.dump(results_data, f, indent=2)
except IOError:
    pass

print("<BACKGROUND_RESULTS>\n" + "\n".join(lines) + "\n</BACKGROUND_RESULTS>")
PYEOF
)

[ -z "$OUTPUT" ] && exit 0

OUTPUT_ESCAPED=$(escape_for_json "$OUTPUT")

cat <<BGEOF
{
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": "${OUTPUT_ESCAPED}"
  }
}
BGEOF
exit 0
