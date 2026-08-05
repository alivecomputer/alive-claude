#!/usr/bin/env bash
# ALIVE x Hermes -- Cron Setup
#
# Emits the `hermes cron create` commands for the ALIVE cron templates.
# DRY RUN by default: the commands are printed to stdout and nothing is
# executed. Pass --apply to actually create the jobs.
#
# Usage: bash setup-crons.sh [--apply] [--deliver TARGET] [--core-only]
#
#   --apply            Execute the `hermes cron create` calls
#                      (default: dry run -- print the commands only)
#   --deliver TARGET   Delivery target for user-facing jobs (default: local).
#                      Keep "local" until you have watched a few runs, then
#                      re-create with telegram/discord/slack if wanted --
#                      eight chatty jobs on a paired channel is a lot of noise.
#   --core-only        Install only the 5 core jobs, skip the 3 optional ones
#   -h, --help         Show this help
#
# Core jobs (the compound loop): alive-morning, alive-project, alive-inbox,
# alive-stash-router, alive-mine. Optional jobs (nudges that overlap the
# morning briefing): alive-health, alive-prune, alive-people.
#
# Maintenance jobs (alive-project, alive-mine) always deliver locally.
#
# Prerequisite -- the cron-template skills must be on Hermes' skill path:
#   # ~/.hermes/config.yaml
#   skills:
#     external_dirs:
#       - <path-to-alive>/hermes/cron-templates

set -euo pipefail

usage() {
  sed -n '2,29p' "$0" | sed 's/^# \{0,1\}//'
}

APPLY=false
DELIVER="local"
CORE_ONLY=false

while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=true ;;
    --deliver)
      shift
      [ $# -gt 0 ] || { echo "error: --deliver needs a target" >&2; exit 2; }
      DELIVER="$1"
      ;;
    --deliver=*) DELIVER="${1#--deliver=}" ;;
    --core-only) CORE_ONLY=true ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "error: unknown argument: $1" >&2
      echo "usage: bash setup-crons.sh [--apply] [--deliver TARGET] [--core-only]" >&2
      exit 2
      ;;
  esac
  shift
done

HERMES_BIN="${HERMES_BIN:-hermes}"
SKILL_DIR="$(cd "$(dirname "$0")/cron-templates" && pwd)"
CREATED=0

# Single-quote a string for display in dry-run output.
sq() {
  local s=$1
  printf "'%s'" "${s//\'/\'\\\'\'}"
}

# create_cron NAME SKILL SCHEDULE DELIVER PROMPT
create_cron() {
  local name=$1 skill=$2 schedule=$3 deliver=$4 prompt=$5
  if ! $APPLY; then
    printf '%s cron create %s %s --name %s --skill %s --deliver %s\n' \
      "$HERMES_BIN" "$(sq "$schedule")" "$(sq "$prompt")" \
      "$(sq "$name")" "$(sq "$skill")" "$(sq "$deliver")"
    return 0
  fi
  if ! "$HERMES_BIN" cron create "$schedule" "$prompt" \
      --name "$name" --skill "$skill" --deliver "$deliver"; then
    echo "error: 'hermes cron create' failed for job '$name' (skill: $skill)" >&2
    echo "Aborting -- $CREATED job(s) were created before the failure." >&2
    exit 1
  fi
  CREATED=$((CREATED + 1))
  echo "  [+] $name" >&2
}

{
  echo "ALIVE x Hermes -- cron setup"
  echo "Mode:     $($APPLY && echo apply || echo 'dry run (nothing executed; re-run with --apply)')"
  echo "Delivery: $DELIVER (maintenance jobs always deliver locally)"
  echo ""
  echo "The cron-template skills must be on Hermes' skill path first:"
  echo "  # ~/.hermes/config.yaml"
  echo "  skills:"
  echo "    external_dirs:"
  echo "      - $SKILL_DIR"
  echo ""
} >&2

# ── Core jobs (the compound loop) ───────────────────────────────

create_cron "ALIVE Morning Briefing" alive-morning "0 7 * * *" "$DELIVER" \
  "Run the alive-morning skill. Read all walnut now.json files, calculate health, surface priorities."

create_cron "ALIVE Projection" alive-project "every 4h" local \
  "Run the alive-project skill. Regenerate now.json projections for all walnuts."

create_cron "ALIVE Inbox Scanner" alive-inbox "every 2h" "$DELIVER" \
  "Run the alive-inbox skill. Scan 03_Inbox/ for unrouted files."

create_cron "ALIVE Stash Router" alive-stash-router "every 4h" "$DELIVER" \
  "Run the alive-stash-router skill. Present pending stash items for routing."

create_cron "ALIVE Nightly Mine" alive-mine "0 2 * * *" local \
  "Run the alive-mine skill. Scan recent session transcripts for context."

# ── Optional jobs (skipped with --core-only) ────────────────────

if ! $CORE_ONLY; then
  create_cron "ALIVE Health Check" alive-health "0 9 * * *" "$DELIVER" \
    "Run the alive-health skill. Flag walnuts past their rhythm."

  create_cron "ALIVE Weekly Prune" alive-prune "0 3 * * 0" "$DELIVER" \
    "Run the alive-prune skill. Suggest log chapters and flag stale insights."

  create_cron "ALIVE People Check" alive-people "0 9 * * 1" "$DELIVER" \
    "Run the alive-people skill. Check stale contacts and cross-reference people mentions."
else
  echo "(--core-only: skipping optional jobs alive-health, alive-prune, alive-people)" >&2
fi

{
  echo ""
  if $APPLY; then
    echo "Done -- created $CREATED job(s)."
    echo "Verify: hermes cron list"
    echo "Test an immediate run: hermes cron tick"
  else
    echo "Dry run complete -- no jobs were created."
    echo "Review the commands above, then re-run with --apply."
  fi
} >&2
