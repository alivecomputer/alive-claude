#!/bin/bash
# Hook: Log Guardian (Codex) -- PreToolUse (apply_patch | Bash)
# Blocks edits to signed log entries. Blocks shell-level rewrites of log.md.
#
# Codex calls apply_patch with either:
#   - tool_input.changes = { "path/log.md": { update: "*** Begin Patch..." } }
#   - tool_input.input   = "*** Begin Patch\n*** Update File: path/log.md\n..."
# We extract the affected paths via extract_apply_patch_files, then for any
# log.md target we look at the diff body for "- signed: squirrel:" lines
# (a removal of a signed line means an edit/delete on signed history).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/alive-common-codex.sh"

read_hook_input
find_world || exit 0

TOOL_NAME=$(json_field "tool_name")

is_log_path() {
  local p="$1"
  echo "$p" | grep -qE '(_kernel/log\.md$|/[^/]+/log\.md$)'
}

inside_world() {
  local p="$1"
  [ -z "${WORLD_ROOT:-}" ] && return 0
  case "$p" in
    "$WORLD_ROOT"/*) return 0 ;;
    /*) return 1 ;;
    *) return 0 ;;  # relative path, assume inside session
  esac
}

case "$TOOL_NAME" in
  apply_patch|edit|edit_file|write|write_file)
    while IFS=$'\t' read -r OP PATH_; do
      [ -z "$PATH_" ] && continue
      is_log_path "$PATH_" || continue
      ABS="$(resolve_path "$PATH_")"
      inside_world "$ABS" || continue

      case "$OP" in
        delete)
          deny_with_reason "log.md is immutable. Cannot delete a walnut log -- it is the signed audit trail."
          ;;
        add)
          # Brand new log.md is fine; save protocol creates them.
          continue
          ;;
        update)
          DIFF=$(extract_apply_patch_diff "$PATH_")
          # Any removal of a signed line => deny
          if echo "$DIFF" | grep -qE '^-[[:space:]]*signed:[[:space:]]*(squirrel:|alive-mcp:)'; then
            deny_with_reason "log.md is immutable. That entry is signed -- add a correction entry at the top instead of editing the signed line."
          fi
          # Removing the YAML frontmatter or any context around a signed entry
          if echo "$DIFF" | grep -qE '^-[[:space:]]*timestamp:' && \
             echo "$DIFF" | grep -qE 'signed: (squirrel:|alive-mcp:)'; then
            deny_with_reason "log.md is immutable. Refusing to rewrite a block that contains signed entries."
          fi
          ;;
      esac
    done < <(extract_apply_patch_files)
    ;;

  Bash|bash|shell|local_shell)
    CMD=$(json_field "tool_input.command")
    [ -z "$CMD" ] && exit 0
    # Catch shell-level rewrites of log.md
    if echo "$CMD" | grep -qE '(>|>>|tee[^|]*|sed -i[^|]*|awk[^|]*-i[^|]*).*(/|^)[^[:space:]]*log\.md([[:space:]]|$|"|'\'')'; then
      deny_with_reason "Refusing shell write to log.md. Use apply_patch to prepend a new entry; signed entries are immutable."
    fi
    if echo "$CMD" | grep -qE '(^|[[:space:];|&])(rm|unlink)([[:space:]]+-[a-zA-Z]+)*[[:space:]]+[^|;&]*log\.md'; then
      deny_with_reason "Refusing to delete log.md -- it is the signed audit trail for this walnut."
    fi
    ;;
esac

exit 0
