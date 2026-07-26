#!/bin/bash
# alive-common-codex.sh -- shared functions for all ALIVE Context System hooks
# (Codex variant). Source this at the top of every hook script.
# Cross-platform: python3 (Mac/Linux) with node fallback (Windows/all).
#
# Codex differs from Claude Code in tool_input shape:
#   - Edit/Write tools do not exist. File mutations come via the `apply_patch`
#     tool whose tool_input either has a `changes` dict keyed by file path,
#     or an `input` string containing a diff envelope with markers like:
#         *** Update File: path/to/file
#         *** Add File: path/to/file
#         *** Delete File: path/to/file
#   - Shell commands come via the `Bash` tool with tool_input.command (same
#     shape as Claude Code).
#
# All guards should call extract_apply_patch_files() to get the list of
# affected file paths regardless of which envelope shape Codex used.

# -- Platform detection --
ALIVE_PLATFORM="unix"
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
  ALIVE_PLATFORM="windows"
fi

# -- JSON runtime detection --
ALIVE_JSON_RT=""
if command -v python3 &>/dev/null && python3 -c "" &>/dev/null 2>&1; then
  ALIVE_JSON_RT="python3"
elif command -v py &>/dev/null && py -3 -c "" &>/dev/null 2>&1; then
  python3() { py -3 "$@"; }
  export -f python3
  ALIVE_JSON_RT="python3"
elif command -v node &>/dev/null; then
  ALIVE_JSON_RT="node"
fi

# Parse multiple fields from JSON in one call.
_json_multi() {
  local json="$1" keys="$2"
  if [ "$ALIVE_JSON_RT" = "python3" ]; then
    printf '%s' "$json" | python3 -c "
import sys,json
d=json.load(sys.stdin)
for k in '''$keys'''.split():
    v=d
    for p in k.split('.'):
        v=v.get(p,'') if isinstance(v,dict) else ''
    print(v if v else '')
" 2>/dev/null || echo ""
  elif [ "$ALIVE_JSON_RT" = "node" ]; then
    printf '%s' "$json" | node -e "
const d=JSON.parse(require('fs').readFileSync(0,'utf8'));
'$keys'.split(' ').forEach(k=>{
  let v=d;k.split('.').forEach(p=>{v=v&&typeof v==='object'?v[p]||'':''});
  console.log(v||'')
})" 2>/dev/null || echo ""
  else
    for _ in $keys; do echo ""; done
  fi
}

# Read JSON input from stdin. Must be called BEFORE any other stdin read.
read_hook_input() {
  HOOK_INPUT=$(cat 2>/dev/null || echo '{}')
  local parsed
  parsed=$(_json_multi "$HOOK_INPUT" "session_id cwd hook_event_name")
  HOOK_SESSION_ID=$(echo "$parsed" | sed -n '1p')
  HOOK_CWD=$(echo "$parsed" | sed -n '2p')
  HOOK_EVENT=$(echo "$parsed" | sed -n '3p')
}

read_session_fields() {
  local parsed
  parsed=$(_json_multi "$HOOK_INPUT" "model source transcript_path")
  HOOK_MODEL=$(echo "$parsed" | sed -n '1p')
  : "${HOOK_MODEL:=unknown}"
  HOOK_SOURCE=$(echo "$parsed" | sed -n '2p')
  HOOK_TRANSCRIPT=$(echo "$parsed" | sed -n '3p')
}

json_field() {
  _json_multi "$HOOK_INPUT" "$1" | head -1
}

read_tool_fields() {
  HOOK_TOOL_NAME=$(json_field "tool_name")
  HOOK_TOOL_INPUT="$HOOK_INPUT"
}

# -----------------------------------------------------------------------------
# extract_apply_patch_files
# -----------------------------------------------------------------------------
# Returns a newline-separated list of file paths affected by the current
# apply_patch tool call. Each line is prefixed with the operation:
#     update<TAB>path/to/file
#     add<TAB>path/to/file
#     delete<TAB>path/to/file
#
# Two envelope shapes are supported:
#   1. tool_input.changes is a dict keyed by file path. Each value is itself
#      a dict whose presence of "add"/"delete" keys indicates the op.
#   2. tool_input.input is a string containing the diff envelope with
#      "*** (Update|Add|Delete) File: <path>" markers.
# -----------------------------------------------------------------------------
extract_apply_patch_files() {
  [ -z "${HOOK_INPUT:-}" ] && return 0
  if [ "$ALIVE_JSON_RT" = "python3" ]; then
    printf '%s' "$HOOK_INPUT" | python3 -c "
import sys, json, re
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
ti = d.get('tool_input') or {}
seen = set()
def emit(op, path):
    path = (path or '').strip()
    if not path: return
    key = (op, path)
    if key in seen: return
    seen.add(key)
    print(f'{op}\t{path}')

changes = ti.get('changes')
if isinstance(changes, dict):
    for path, spec in changes.items():
        op = 'update'
        if isinstance(spec, dict):
            if spec.get('add') is not None or spec.get('add_file') is not None:
                op = 'add'
            elif spec.get('delete') is not None or spec.get('delete_file') is not None:
                op = 'delete'
        emit(op, path)

inp = ti.get('input')
if isinstance(inp, str) and inp:
    for m in re.finditer(r'^\*\*\* (Update|Add|Delete) File: (.+?)\s*$', inp, re.MULTILINE):
        op = m.group(1).lower()
        path = m.group(2).strip()
        emit(op, path)
    for m in re.finditer(r'^\*\*\* Move to: (.+?)\s*$', inp, re.MULTILINE):
        emit('add', m.group(1).strip())
" 2>/dev/null
  elif [ "$ALIVE_JSON_RT" = "node" ]; then
    printf '%s' "$HOOK_INPUT" | node -e "
let raw='';process.stdin.on('data',c=>raw+=c);process.stdin.on('end',()=>{
  let d;try{d=JSON.parse(raw)}catch(e){return}
  const ti=(d&&d.tool_input)||{};
  const seen=new Set();
  const emit=(op,p)=>{p=(p||'').trim();if(!p)return;const k=op+'\t'+p;if(seen.has(k))return;seen.add(k);process.stdout.write(k+'\n')};
  const c=ti.changes;
  if(c&&typeof c==='object'){
    for(const path of Object.keys(c)){
      const spec=c[path];let op='update';
      if(spec&&typeof spec==='object'){
        if(spec.add!=null||spec.add_file!=null) op='add';
        else if(spec.delete!=null||spec.delete_file!=null) op='delete';
      }
      emit(op,path);
    }
  }
  const inp=ti.input;
  if(typeof inp==='string'&&inp){
    const re=/^\*\*\* (Update|Add|Delete) File: (.+?)\s*$/gm;
    let m;while((m=re.exec(inp))!==null){emit(m[1].toLowerCase(),m[2].trim())}
    const re2=/^\*\*\* Move to: (.+?)\s*$/gm;
    while((m=re2.exec(inp))!==null){emit('add',m[1].trim())}
  }
})" 2>/dev/null
  fi
}

# Convenience: just the paths, no op prefix.
extract_apply_patch_paths() {
  extract_apply_patch_files | awk -F'\t' '{print $2}'
}

# Extract the diff body for a specific file from tool_input.input.
extract_apply_patch_diff() {
  local target="$1"
  [ -z "${HOOK_INPUT:-}" ] && return 0
  [ -z "$target" ] && return 0
  if [ "$ALIVE_JSON_RT" = "python3" ]; then
    printf '%s' "$HOOK_INPUT" | python3 -c "
import sys, json, re
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
target = '''$target'''
ti = d.get('tool_input') or {}
inp = ti.get('input') or ''
if isinstance(inp, str) and inp:
    pat = re.compile(r'^\*\*\* (Update|Add|Delete) File: (.+?)\s*$', re.MULTILINE)
    matches = list(pat.finditer(inp))
    for i, m in enumerate(matches):
        if m.group(2).strip() == target:
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(inp)
            sys.stdout.write(inp[start:end])
            break
ch = ti.get('changes')
if isinstance(ch, dict) and target in ch:
    spec = ch[target]
    if isinstance(spec, dict):
        for k in ('update','add','add_file','content','contents','new'):
            v = spec.get(k)
            if isinstance(v, str):
                sys.stdout.write(v)
                break
" 2>/dev/null
  fi
}

# Find the world root.
find_world() {
  local dir="${HOOK_CWD:-${CODEX_PROJECT_DIR:-${CLAUDE_PROJECT_DIR:-$PWD}}}"

  local check="$dir"
  while [ "$check" != "/" ]; do
    if [ -d "$check/.alive" ] && [ -d "$check/01_Archive" ] && [ -d "$check/02_Life" ]; then
      WORLD_ROOT="$check"
      return 0
    fi
    check="$(dirname "$check")"
  done

  local config_file="${HOME}/.config/alive/world-root"
  if [ ! -f "$config_file" ] && [ -f "${HOME}/.config/walnut/world-root" ]; then
    config_file="${HOME}/.config/walnut/world-root"
  fi
  if [ -f "$config_file" ]; then
    local stored_root
    IFS= read -r stored_root < "$config_file" || true
    stored_root="${stored_root%$'\r'}"
    if [ -d "$stored_root/.alive" ] && [ -d "$stored_root/01_Archive" ] && [ -d "$stored_root/02_Life" ]; then
      WORLD_ROOT="$stored_root"
      return 0
    fi
  fi

  if [ -n "${ALIVE_WORLD_ROOT:-}" ]; then
    if [ -d "$ALIVE_WORLD_ROOT/.alive" ] && [ -d "$ALIVE_WORLD_ROOT/01_Archive" ] && [ -d "$ALIVE_WORLD_ROOT/02_Life" ]; then
      WORLD_ROOT="$ALIVE_WORLD_ROOT"
      return 0
    fi
  fi

  return 1
}

# Render the previously generated bounded orientation cache. Hooks must never
# build or crawl the world. Cache problems are surfaced as a short notice so
# the next explicit save can repair them without treating startup as a refresh.
read_bounded_orientation() {
  local renderer="$PLUGIN_ROOT/scripts/orientation.py"
  [ -f "$renderer" ] || {
    printf 'ALIVE orientation cache cannot be rendered because the packaged renderer is missing.'
    return 0
  }
  ALIVE_WORLD_ROOT="$WORLD_ROOT" ALIVE_ORIENTATION_RENDERER="$renderer" python3 -c '
import json, os, subprocess, sys
from pathlib import Path

world = Path(os.environ["ALIVE_WORLD_ROOT"])
orientation = world / ".alive" / "_orientation.json"
index = world / ".alive" / "_index.json"

def notice(text):
    print(text)
    raise SystemExit(0)

if not orientation.is_file():
    notice("ALIVE orientation cache is missing. Run explicit alive-save to refresh it.")
try:
    encoded = orientation.read_bytes()
    if len(encoded) > 8192:
        raise ValueError("oversized")
    payload = json.loads(encoded.decode("utf-8"))
except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
    notice("ALIVE orientation cache is invalid. Run explicit alive-save to refresh it.")
if not isinstance(payload, dict):
    notice("ALIVE orientation cache is invalid. Run explicit alive-save to refresh it.")
schema = payload.get("schema_version")
if type(schema) is not int or schema != 1:
    notice("ALIVE orientation cache has an unsupported schema. Run explicit alive-save to refresh it.")
if not index.is_file():
    notice("ALIVE orientation source index is missing. Run explicit alive-save to refresh it.")
source = payload.get("source_index")
try:
    current = index.stat()
    source_size = source["size"]
    source_mtime = source["mtime_ns"]
except (OSError, KeyError, TypeError):
    notice("ALIVE orientation cache is invalid. Run explicit alive-save to refresh it.")
if (
    type(source_size) is not int
    or type(source_mtime) is not int
    or current.st_size != source_size
    or current.st_mtime_ns != source_mtime
):
    notice("ALIVE orientation cache is stale. Run explicit alive-save to refresh it.")
rendered = subprocess.run(
    [sys.executable, os.environ["ALIVE_ORIENTATION_RENDERER"], "render", str(world), "--limit", "3"],
    text=True,
    capture_output=True,
    timeout=5,
)
if rendered.returncode != 0 or not rendered.stdout.strip():
    notice("ALIVE orientation cache is invalid. Run explicit alive-save to refresh it.")
print(rendered.stdout.strip())
' 2>/dev/null || printf 'ALIVE orientation cache is invalid. Run explicit alive-save to refresh it.'
}

# Keep lifecycle context within Codex's 8192-byte limit while retaining the
# complete small orientation rendering whenever possible. Recovery context is
# clipped first; UTF-8 is decoded only at complete character boundaries.
compose_bounded_orientation_context() {
  local recovery_context="$1" orientation="${2:-}"
  {
    printf '%s' "$recovery_context"
    printf '\0'
    printf '%s' "$orientation"
  } | python3 -c '
import sys

MAX_BYTES = 8192
ORIENTATION_BUDGET = 4096
TRUNCATION = "\n[Context truncated to fit Codex hook limit.]"

def byte_length(value):
    return len(value.encode("utf-8"))

def clipped(value, limit):
    if byte_length(value) <= limit:
        return value
    suffix = TRUNCATION.encode("utf-8")
    if limit <= len(suffix):
        return suffix[:limit].decode("utf-8", "ignore")
    prefix = value.encode("utf-8")[:limit - len(suffix)].decode("utf-8", "ignore")
    return prefix + TRUNCATION

raw = sys.stdin.buffer.read()
recovery_raw, separator_byte, orientation_raw = raw.partition(b"\0")
if not separator_byte:
    orientation_raw = b""
recovery = recovery_raw.decode("utf-8", "replace")
orientation = clipped(orientation_raw.decode("utf-8", "replace"), ORIENTATION_BUDGET)
separator = "\n\n" if recovery and orientation else ""
recovery = clipped(recovery, MAX_BYTES - byte_length(orientation) - byte_length(separator))
print(recovery + separator + orientation, end="")
'
}

# Resolve a possibly-relative path against the session cwd.
resolve_path() {
  local p="$1"
  [ -z "$p" ] && return 0
  if [[ "$p" != /* ]]; then
    printf '%s/%s' "${HOOK_CWD:-$PWD}" "$p"
  else
    printf '%s' "$p"
  fi
}

# Escape string for JSON embedding.
escape_for_json() {
  if [ "$ALIVE_JSON_RT" = "python3" ]; then
    printf '%s' "$1" | python3 -c "import sys,json; sys.stdout.write(json.dumps(sys.stdin.read(), ensure_ascii=False)[1:-1])"
  elif [ "$ALIVE_JSON_RT" = "node" ]; then
    printf '%s' "$1" | node -e "let d='';process.stdin.setEncoding('utf8');process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>process.stdout.write(JSON.stringify(d).slice(1,-1)))"
  else
    return 1
  fi
}

# Emit a Codex deny decision and exit.
deny_with_reason() {
  local reason="$1"
  local escaped
  escaped=$(escape_for_json "$reason")
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$escaped"
  exit 0
}

# Emit current Codex hook-specific context without legacy top-level fields.
emit_additional_context() {
  local event_name="$1" context="$2"
  ALIVE_EVENT_NAME="$event_name" ALIVE_CONTEXT="$context" python3 -c '
import json, os
print(json.dumps({"hookSpecificOutput": {
    "hookEventName": os.environ["ALIVE_EVENT_NAME"],
    "additionalContext": os.environ["ALIVE_CONTEXT"],
}}, separators=(",", ":")))
'
}

# Persist a bounded recovery record in plugin-owned storage. This records what
# was already saved; it does not claim that unsaved conversational state was
# written to the walnut.
write_recovery_record() {
  local session_id="${1:-${HOOK_SESSION_ID:-}}" event_name="${2:-${HOOK_EVENT:-unknown}}"
  [ -n "$session_id" ] || return 1
  [ -n "${WORLD_ROOT:-}" ] || return 1
  local entry="$WORLD_ROOT/.alive/_squirrels/$session_id.yaml"
  [ -f "$entry" ] || return 1
  local plugin_data="${PLUGIN_DATA:-${CLAUDE_PLUGIN_DATA:-}}"
  [ -n "$plugin_data" ] || return 1
  local safe_session
  safe_session=$(printf '%s' "$session_id" | tr -cd 'A-Za-z0-9._-')
  [ -n "$safe_session" ] || return 1
  local recovery_dir="$plugin_data/recovery"
  mkdir -p "$recovery_dir"
  chmod 700 "$recovery_dir" 2>/dev/null || true
  ALIVE_ENTRY="$entry" ALIVE_RECOVERY_FILE="$recovery_dir/$safe_session.json" \
    ALIVE_RECOVERY_WORLD="$WORLD_ROOT" ALIVE_RECOVERY_SESSION="$session_id" \
    ALIVE_RECOVERY_EVENT="$event_name" python3 -c '
import datetime, json, os, pathlib, tempfile

entry = pathlib.Path(os.environ["ALIVE_ENTRY"])
values = {}
for line in entry.read_text(encoding="utf-8", errors="replace").splitlines():
    if ":" not in line or line[:1].isspace():
        continue
    key, value = line.split(":", 1)
    values.setdefault(key.strip(), value.strip())

def scalar(value):
    if not value or value in {"null", "~"}:
        return ""
    if value.startswith(("\"", "[", "{")):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, (str, int, float, bool)) else value
        except json.JSONDecodeError:
            pass
    return value

payload = {
    "format": 1,
    "runtime_id": "squirrel.core@3.3",
    "session_id": os.environ["ALIVE_RECOVERY_SESSION"],
    "world": os.environ["ALIVE_RECOVERY_WORLD"],
    "walnut": scalar(values.get("walnut", "")),
    "recovery_state": scalar(values.get("recovery_state", "")),
    "saves": int(scalar(values.get("saves", "0")) or 0),
    "event": os.environ["ALIVE_RECOVERY_EVENT"],
    "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
target = pathlib.Path(os.environ["ALIVE_RECOVERY_FILE"])
fd, name = tempfile.mkstemp(prefix=".recovery-", dir=target.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.chmod(name, 0o600)
    os.replace(name, target)
finally:
    pathlib.Path(name).unlink(missing_ok=True)
' 2>/dev/null
}
