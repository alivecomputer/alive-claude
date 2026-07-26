#!/bin/bash
# Hook: Root Guardian (Codex) -- PreToolUse (apply_patch | Bash)
# Blocks writes to the world root that aren't domain folders or hidden files.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/alive-common-codex.sh"

read_hook_input
find_world || exit 0

TOOL_NAME=$(json_field "tool_name")

ALLOWED_DOMAINS_RE='^(01_Archive|02_Life|03_Inbox|04_Ventures|05_Experiments)$'

# Check whether a path lands directly in the world root and isn't an
# allow-listed name. Returns 0 (yes, block) / 1 (no, allow).
should_block_root_path() {
  local raw="$1"
  local p
  p="$(resolve_path "$raw")"
  local dir name
  dir="$(dirname "$p")"
  name="$(basename "$p")"

  [ "$dir" = "$WORLD_ROOT" ] || return 1
  [[ "$name" == .* ]] && return 1
  if [[ "$name" =~ $ALLOWED_DOMAINS_RE ]]; then
    return 1
  fi
  if [ "$name" = "Icon" ] || [ "$name" = $'Icon\r' ]; then
    return 1
  fi
  return 0
}

REASON_FOR() {
  local fname="$1"
  printf 'Cannot write %s to the world root. Nothing lives at root except the 5 domain folders (01_Archive through 05_Experiments) and hidden files. Route this to the right place: if it belongs to a walnut, put it in that walnut'\''s _kernel/ or as a deliverable in the walnut root. If it'\''s an input, put it in 03_Inbox/. If it'\''s a new project, create a walnut with alive:create-walnut. Ask the human where it should go.' "'$fname'"
}

case "$TOOL_NAME" in
  apply_patch|edit|edit_file|write|write_file)
    while IFS=$'\t' read -r OP PATH_; do
      [ -z "$PATH_" ] && continue
      [ "$OP" = "delete" ] && continue   # deletion of root cruft is fine
      if should_block_root_path "$PATH_"; then
        deny_with_reason "$(REASON_FOR "$(basename "$PATH_")")"
      fi
    done < <(extract_apply_patch_files)
    ;;

  Bash|bash|shell|local_shell)
    CMD=$(json_field "tool_input.command")
    [ -z "$CMD" ] && exit 0
    # Look for shell mutations whose target is at the world root.
    # We extract candidate target tokens following >, >>, tee, cp, mv, sed -i.
    if [ "$ALIVE_JSON_RT" = "python3" ]; then
      TARGETS=$(printf '%s' "$CMD" | python3 -c "
import sys, shlex, re
cmd = sys.stdin.read().strip()
out = set()
for part in re.split(r'[;&|]+', cmd):
    part = part.strip()
    try:
        toks = shlex.split(part)
    except ValueError:
        toks = part.split()
    if not toks: continue
    head = toks[0]
    if head in ('cp','mv'):
        # last non-flag arg is destination
        args = [t for t in toks[1:] if not t.startswith('-')]
        if args: out.add(args[-1])
    if head == 'tee':
        args = [t for t in toks[1:] if not t.startswith('-')]
        out.update(args)
    if head == 'sed' and any(t.startswith('-i') for t in toks):
        args = [t for t in toks[1:] if not t.startswith('-') and not t.startswith('s/') and not t.startswith('/')]
        # Heuristic: last arg is the file
        if len(args)>=1: out.add(args[-1])
    # redirection: > file or >> file
    for m in re.finditer(r'>>?\s*([^\s|;&<>]+)', part):
        out.add(m.group(1).strip('\"\\''))
for t in out:
    print(t)
" 2>/dev/null)
      while IFS= read -r tgt; do
        [ -z "$tgt" ] && continue
        if should_block_root_path "$tgt"; then
          deny_with_reason "$(REASON_FOR "$(basename "$tgt")")"
        fi
      done <<< "$TARGETS"
    fi
    ;;
esac

exit 0
