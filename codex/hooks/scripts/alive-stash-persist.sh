#!/bin/bash
# Hook: Stash Persist (Codex) -- PostToolUse (apply_patch)
# Replaces the Claude Code PreCompact protection. Codex doesn't have a
# pre-compact event, so on every apply_patch we snapshot the current
# session's stash state from the squirrel YAML to JSON at:
#     .alive/_squirrels/<session>/stash.json
#
# Why every apply_patch: Codex compaction is opaque, can happen between any
# two tool calls. Persisting on every write means worst-case we lose only
# what was added between the last apply_patch and the compact. Cheap,
# debounced, never blocks.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/alive-common-codex.sh"

read_hook_input
find_world || exit 0

SESSION_ID="${HOOK_SESSION_ID}"
[ -z "$SESSION_ID" ] && exit 0

SQUIRRELS_DIR="$WORLD_ROOT/.alive/_squirrels"
[ -d "$SQUIRRELS_DIR" ] || exit 0

# Locate the squirrel YAML (exact session match, then most-recent active)
ENTRY=""
if [ -f "$SQUIRRELS_DIR/$SESSION_ID.yaml" ]; then
  ENTRY="$SQUIRRELS_DIR/$SESSION_ID.yaml"
else
  ENTRY=$(ls -t "$SQUIRRELS_DIR"/*.yaml 2>/dev/null | while read -r f; do
    grep -q 'ended: null' "$f" 2>/dev/null && echo "$f" && break
  done || true)
fi
[ -z "${ENTRY:-}" ] && exit 0
[ -f "$ENTRY" ] || exit 0

# Debounce: skip if we persisted in the last 10s for this session
MARKER="/tmp/alive-stash-persist-${SESSION_ID}"
if [ -f "$MARKER" ]; then
  if stat --version >/dev/null 2>&1; then
    MARKER_MTIME=$(stat -c %Y "$MARKER" 2>/dev/null || echo "0")
  else
    MARKER_MTIME=$(stat -f %m "$MARKER" 2>/dev/null || echo "0")
  fi
  AGE=$(( $(date +%s) - MARKER_MTIME ))
  [ "$AGE" -lt 10 ] && exit 0
fi
touch "$MARKER"

# Build target directory: .alive/_squirrels/<session>/stash.json
SESSION_DIR="$SQUIRRELS_DIR/$SESSION_ID"
mkdir -p "$SESSION_DIR" 2>/dev/null || exit 0
TARGET="$SESSION_DIR/stash.json"

# Convert YAML -> JSON via python3. Pull the `stash:` subtree (or whole doc
# if no stash key). Atomic write via temp file + mv.
if [ "$ALIVE_JSON_RT" = "python3" ]; then
  python3 - "$ENTRY" "$TARGET" <<'PY' 2>/dev/null || exit 0
import sys, json, os, tempfile
src, dst = sys.argv[1], sys.argv[2]
try:
    import yaml  # PyYAML
except ImportError:
    # No PyYAML -- fall back to a tiny parser that grabs only top-level keys
    yaml = None
data = None
if yaml is not None:
    try:
        with open(src, 'r', encoding='utf-8') as fh:
            data = yaml.safe_load(fh) or {}
    except Exception:
        data = None
if data is None:
    # Minimal fallback: bag the raw text under "raw"
    try:
        with open(src, 'r', encoding='utf-8') as fh:
            data = {'raw': fh.read()}
    except Exception:
        sys.exit(0)
stash = data.get('stash') if isinstance(data, dict) else None
payload = {
    'session_id': data.get('session_id') if isinstance(data, dict) else None,
    'persisted_at': __import__('datetime').datetime.utcnow().isoformat() + 'Z',
    'stash': stash if stash is not None else {},
    'source_yaml': src,
}
fd, tmp = tempfile.mkstemp(prefix='.stash.', dir=os.path.dirname(dst))
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        json.dump(payload, fh, indent=2, default=str, ensure_ascii=False)
    os.replace(tmp, dst)
except Exception:
    try: os.unlink(tmp)
    except OSError: pass
    sys.exit(0)
PY
fi

exit 0
