#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/alive-common-codex.sh"

read_hook_input
find_world || exit 0
projector="${PLUGIN_ROOT:-$(cd "$script_dir/../.." && pwd)}/scripts/project.py"
indexer="${PLUGIN_ROOT:-$(cd "$script_dir/../.." && pwd)}/scripts/generate-index.py"
[ -f "$projector" ] && [ -f "$indexer" ] || exit 0

projected=0
index_needed=0
while IFS=$'\t' read -r operation path; do
  [ -n "$path" ] || continue
  absolute=$(resolve_path "$path")
  case "$absolute" in
    */_kernel/log.md|*/_kernel/tasks.json|*/_kernel/insights.md|*/context.manifest.yaml)
      check="$(dirname "$absolute")"
      walnut=""
      while [ "$check" != "/" ] && [ "$check" != "$WORLD_ROOT" ]; do
        if [ "$(basename "$check")" = "_kernel" ]; then
          walnut="$(dirname "$check")"
          break
        fi
        if [ -d "$check/_kernel" ]; then
          walnut="$check"
          break
        fi
        check="$(dirname "$check")"
      done
      if [ -n "$walnut" ]; then
        python3 "$projector" --walnut "$walnut" >/dev/null
        projected=1
        index_needed=1
      fi
      ;;
    */_kernel/key.md|*/_kernel/now.json|*/key.md)
      index_needed=1
      ;;
  esac
done < <(extract_apply_patch_files)

if [ "$index_needed" = "1" ] || [ "$projected" = "1" ]; then
  python3 "$indexer" "$WORLD_ROOT" --build-orientation >/dev/null
fi
