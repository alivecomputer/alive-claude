#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/alive-common-codex.sh"

read_hook_input
[ -n "${HOOK_SESSION_ID:-}" ] || exit 0
find_world || exit 0
write_recovery_record "$HOOK_SESSION_ID" "PostCompact" || true
