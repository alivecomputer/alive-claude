#!/bin/bash
# Hook: Rules Guardian (Codex) -- PreToolUse (apply_patch | Bash)
# Blocks edits to plugin-managed files in .alive/, .claude/, plugin cache, AND
# the Codex plugin tree itself ($PLUGIN_ROOT/{rules,skills,hooks,
# templates,AGENTS.md}).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/alive-common-codex.sh"

read_hook_input
find_world || true   # rules guardian works even outside a world (plugin tree)

TOOL_NAME=$(json_field "tool_name")

DENY_REASON="This file is managed by the ALIVE Context System plugin and will be overwritten on update. Put your customizations in .alive/overrides.md instead."

is_protected() {
  local p_in="$1"
  local p
  p="$(resolve_path "$p_in")"

  # Always allow user overrides / preferences / world key / walnut config
  case "$p" in
    */overrides.md|*/user-overrides.md|*/preferences.yaml|*/_kernel/config.yaml|*/config.yaml)
      return 1
      ;;
  esac

  # Codex plugin tree is fully protected
  if [ -n "${PLUGIN_ROOT:-}" ]; then
    case "$p" in
      "$PLUGIN_ROOT"/rules/*|"$PLUGIN_ROOT"/skills/*|\
      "$PLUGIN_ROOT"/hooks/*|"$PLUGIN_ROOT"/templates/*|\
      "$PLUGIN_ROOT"/AGENTS.md)
        return 0
        ;;
    esac
  fi

  # Same for Claude Code plugin root if both happen to be set
  if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
    case "$p" in
      "$CLAUDE_PLUGIN_ROOT"/rules/*|"$CLAUDE_PLUGIN_ROOT"/skills/*|\
      "$CLAUDE_PLUGIN_ROOT"/hooks/*|"$CLAUDE_PLUGIN_ROOT"/templates/*|\
      "$CLAUDE_PLUGIN_ROOT"/AGENTS.md)
        return 0
        ;;
    esac
  fi

  if [ -z "${WORLD_ROOT:-}" ]; then
    return 1
  fi

  # Allow .alive/key.md (user identity)
  if [ "$p" = "$WORLD_ROOT/.alive/key.md" ]; then
    return 1
  fi

  # Block plugin-managed rules in .alive/rules/
  case "$p" in
    "$WORLD_ROOT"/.alive/rules/*)
      case "$(basename "$p")" in
        voice.md|squirrels.md|human.md|world.md|bundles.md|standards.md)
          return 0 ;;
      esac
      ;;
  esac

  # Block .alive/agents.md
  if [ "$p" = "$WORLD_ROOT/.alive/agents.md" ] || [ "$p" = "$WORLD_ROOT/.alive/AGENTS.md" ]; then
    return 0
  fi

  # Block .claude/CLAUDE.md
  if [ "$p" = "$WORLD_ROOT/.claude/CLAUDE.md" ]; then
    return 0
  fi

  # Block .claude/rules/ files
  case "$p" in
    "$WORLD_ROOT"/.claude/rules/*)
      case "$(basename "$p")" in
        voice.md|squirrels.md|human.md|world.md|bundles.md|standards.md)
          return 0 ;;
      esac
      ;;
  esac

  # Block plugin cache
  case "$p" in
    */.claude/plugins/cache/alivecontext/alive/*) return 0 ;;
    */.codex/plugins/cache/alivecontext/alive/*) return 0 ;;
  esac

  return 1
}

case "$TOOL_NAME" in
  apply_patch|edit|edit_file|write|write_file)
    while IFS=$'\t' read -r OP PATH_; do
      [ -z "$PATH_" ] && continue
      if is_protected "$PATH_"; then
        deny_with_reason "$DENY_REASON Path: $PATH_"
      fi
    done < <(extract_apply_patch_files)
    ;;

  Bash|bash|shell|local_shell)
    CMD=$(json_field "tool_input.command")
    [ -z "$CMD" ] && exit 0
    # Quick word-list scan: if any of these substrings appear AND the command
    # contains a write-ish op, deny. This is intentionally conservative -- we
    # want to catch curl > .alive/rules/voice.md style attacks.
    PROTECTED_TOKENS=(
      ".alive/rules/voice.md" ".alive/rules/squirrels.md" ".alive/rules/human.md"
      ".alive/rules/world.md" ".alive/rules/bundles.md" ".alive/rules/standards.md"
      ".alive/agents.md" ".alive/AGENTS.md" ".claude/CLAUDE.md"
      ".claude/rules/voice.md" ".claude/rules/squirrels.md" ".claude/rules/human.md"
      ".claude/rules/world.md" ".claude/rules/bundles.md" ".claude/rules/standards.md"
      ".claude/plugins/cache/alivecontext/alive"
      ".codex/plugins/cache/alivecontext/alive"
    )
    if [ -n "${PLUGIN_ROOT:-}" ]; then
      PROTECTED_TOKENS+=("$PLUGIN_ROOT/rules" "$PLUGIN_ROOT/skills" "$PLUGIN_ROOT/hooks" "$PLUGIN_ROOT/templates" "$PLUGIN_ROOT/AGENTS.md")
    fi
    if echo "$CMD" | grep -qE '(>|>>|tee|sed -i|cp[[:space:]]+|mv[[:space:]]+|rm[[:space:]]+|curl[^|]*-o|wget[^|]*-O)'; then
      for tok in "${PROTECTED_TOKENS[@]}"; do
        if [[ "$CMD" == *"$tok"* ]]; then
          deny_with_reason "$DENY_REASON Refusing shell mutation of plugin-managed path: $tok"
        fi
      done
    fi
    ;;
esac

exit 0
