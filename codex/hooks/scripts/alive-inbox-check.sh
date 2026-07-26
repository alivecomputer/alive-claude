#!/bin/bash
# Hook: Inbox Check (Codex) -- PostToolUse (apply_patch)
# After any apply_patch, check 03_Inbox/ for unrouted items. If any exist,
# silently emit additionalContext nudging the squirrel to capture them.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/alive-common-codex.sh"

read_hook_input
find_world || exit 0

# Only fire when at least one written path looks like now.json/now.md (same
# trigger as Claude Code variant) -- keeps the nudge tied to save events.
TRIGGERED=0
while IFS=$'\t' read -r OP PATH_; do
  [ -z "$PATH_" ] && continue
  case "$PATH_" in
    */_kernel/now.json|*/_kernel/_generated/now.json|*/now.json|*/now.md)
      TRIGGERED=1; break ;;
  esac
done < <(extract_apply_patch_files)

[ "$TRIGGERED" = "1" ] || exit 0

INPUTS_DIR="$WORLD_ROOT/03_Inbox"
[ -d "$INPUTS_DIR" ] || exit 0

COUNT=0
while IFS= read -r -d '' entry; do
  name="$(basename "$entry")"
  case "$name" in
    .DS_Store|.gitkeep|.keep) continue ;;
  esac
  COUNT=$((COUNT + 1))
done < <(find "$INPUTS_DIR" -mindepth 1 -maxdepth 1 -print0 2>/dev/null)

[ "$COUNT" -eq 0 ] && exit 0

NUDGE="Inbox has ${COUNT} item(s) in 03_Inbox/. If the human isn't in the middle of something, suggest running alive:capture-context to clear the inbox."
ESCAPED=$(escape_for_json "$NUDGE")

cat <<EOF
{
  "hookSpecificOutput": {
    "hookEventName": "PostToolUse",
    "additionalContext": "${ESCAPED}"
  }
}
EOF

exit 0
