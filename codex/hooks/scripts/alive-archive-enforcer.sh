#!/bin/bash
# Hook: Archive Enforcer (Codex) -- PreToolUse (apply_patch | Bash)
# Two jobs:
#   1. Block apply_patch writes (any op) into 01_Archive/.
#   2. Block shell rm/rmdir/unlink/mv into trash anywhere inside the world,
#      renaming the targets to "(Marked for Deletion)" so the human can
#      review them in Finder.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/alive-common-codex.sh"

read_hook_input
find_world || exit 0

TOOL_NAME=$(json_field "tool_name")

is_in_archive() {
  local p
  p="$(resolve_path "$1")"
  case "$p" in
    "$WORLD_ROOT"/01_Archive|"$WORLD_ROOT"/01_Archive/*) return 0 ;;
    *) return 1 ;;
  esac
}

is_in_world() {
  local p="$1"
  case "$p" in
    "$WORLD_ROOT"|"$WORLD_ROOT"/*) return 0 ;;
    *) return 1 ;;
  esac
}

case "$TOOL_NAME" in
  apply_patch|edit|edit_file|write|write_file)
    while IFS=$'\t' read -r OP PATH_; do
      [ -z "$PATH_" ] && continue
      if is_in_archive "$PATH_"; then
        deny_with_reason "Refusing apply_patch on 01_Archive/. Archive is read-only -- create a new walnut or work in 02_Life/04_Ventures/05_Experiments instead. Path: $PATH_"
      fi
    done < <(extract_apply_patch_files)
    exit 0
    ;;

  Bash|bash|shell|local_shell)
    : # fall through to rm-protection block
    ;;

  *)
    exit 0
    ;;
esac

COMMAND=$(json_field "tool_input.command")
[ -z "$COMMAND" ] && exit 0

if ! echo "$COMMAND" | grep -qE '(^|[[:space:];|&])(rm|rmdir|unlink)([[:space:]]|$)'; then
  exit 0
fi

# Extract target paths via shlex
TARGET=$(echo "$COMMAND" | python3 -c "
import sys, shlex, re
cmd = sys.stdin.buffer.read().decode('utf-8','replace').strip()
for part in re.split(r'[;&|]+', cmd):
    part = part.strip()
    try: tokens = shlex.split(part)
    except ValueError: tokens = part.split()
    found = False
    for t in tokens:
        if not found:
            if t in ('rm', 'rmdir', 'unlink'):
                found = True
            continue
        if not t.startswith('-'):
            print(t)
" 2>/dev/null)

RESOLVE_DIR="${HOOK_CWD:-$PWD}"

RENAMED=""
NOT_FOUND=""

while IFS= read -r path; do
  [ -z "$path" ] && continue
  if [[ "$path" != /* ]]; then
    resolved="$RESOLVE_DIR/$path"
  else
    resolved="$path"
  fi

  case "$resolved" in
    "$WORLD_ROOT"|"$WORLD_ROOT"/*)
      if [ -e "$resolved" ]; then
        DIRNAME=$(dirname "$resolved")
        BASENAME=$(basename "$resolved")
        MARKED="${DIRNAME}/${BASENAME} (Marked for Deletion)"
        mv "$resolved" "$MARKED" 2>/dev/null || true
        if [[ "$OSTYPE" == "darwin"* ]]; then
          open "$DIRNAME" 2>/dev/null || true
        elif command -v xdg-open &>/dev/null; then
          xdg-open "$DIRNAME" 2>/dev/null || true
        fi
        RENAMED="${RENAMED}${BASENAME}, "
      else
        NOT_FOUND="${NOT_FOUND}$(basename "$resolved"), "
      fi
      ;;
  esac
done <<< "$TARGET"

if [ -n "$RENAMED" ] || [ -n "$NOT_FOUND" ]; then
  REASON=""
  if [ -n "$RENAMED" ]; then
    REASON="Renamed to (Marked for Deletion): ${RENAMED%, }. Review in your file manager and delete manually if intended."
  fi
  if [ -n "$NOT_FOUND" ]; then
    [ -n "$REASON" ] && REASON="$REASON "
    REASON="${REASON}Not found (may already be removed): ${NOT_FOUND%, }."
  fi
  deny_with_reason "$REASON"
fi

exit 0
