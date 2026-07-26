---
name: alive-boot-sequence
description: "The living system. Activates background crons and dispatches them in sequence — cinematic ASCII UI at every step. Run in a dedicated session. The system boots, agents fan out, results stream back. OG Macintosh energy."
---

# Boot

The living system starts here. This skill activates background mode and dispatches all due crons in sequence. Every step is visual. Every agent return renders. Full log of everything that happened.

Run this in a dedicated session — not your working session. This is the engine room.

---

## Step 1 — Boot Screen

Show the boot screen immediately. No file reads first. This is the first thing the human sees.

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│                                                         │
│              █████╗ ██╗     ██╗██╗   ██╗███████╗        │
│             ██╔══██╗██║     ██║██║   ██║██╔════╝        │
│             ███████║██║     ██║██║   ██║█████╗          │
│             ██╔══██║██║     ██║╚██╗ ██╔╝██╔══╝          │
│             ██║  ██║███████╗██║ ╚████╔╝ ███████╗        │
│             ╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝  ╚══════╝        │
│                                                         │
│              B O O T   S E Q U E N C E                  │
│              ─────────────────────────                  │
│                                                         │
│              the living system                          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Step 2 — System Check

Read `.alive/_background/crons.json`. Enable background mode (`enabled: true`). Count crons, check which are due.

```
┌─ SYSTEM CHECK ──────────────────────────────────────────┐
│                                                         │
│  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░  scanning crons...    │
│                                                         │
│  crons.json          ✓ loaded                           │
│  background mode     ✓ enabled                          │
│  max concurrent      3                                  │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  QUEUE                                          │    │
│  │                                                 │    │
│  │  01  gmail-parse        30m   ● due             │    │
│  │  02  inbox-route        30m   ○ 28m remaining   │    │
│  │  03  slack-sync         30m   ● due             │    │
│  │  04  fathom-sync        60m   ● due             │    │
│  │  ...                                            │    │
│  │  15  invoice-chase      24h   ● due             │    │
│  │                                                 │    │
│  │  N due  ·  M running  ·  K completed            │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Show actual data — which crons are due (never run or interval elapsed), which are still on cooldown.

## Step 3 — Dispatch Wave

Dispatch up to `max_concurrent` crons simultaneously as background agents. Show each dispatch:

```
┌─ DISPATCHING ───────────────────────────────────────────┐
│                                                         │
│  ▸ gmail-parse                                          │
│    scanning inbox, drafting replies                      │
│    ████░░░░░░░░░░░░░░░░░░  dispatched                  │
│                                                         │
│  ▸ slack-sync                                           │
│    pulling sz-inbox-* channels                          │
│    ████░░░░░░░░░░░░░░░░░░  dispatched                  │
│                                                         │
│  ▸ fathom-sync                                          │
│    checking for new transcripts                         │
│    ████░░░░░░░░░░░░░░░░░░  dispatched                  │
│                                                         │
│  3 agents in flight  ·  12 in queue                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

For each dispatch:
1. Read the cron's job spec (the hook would normally do this, but in boot mode the skill drives)
2. Mark running in crons.json
3. Dispatch Agent with `run_in_background: true`
4. Show the dispatch render

## Step 4 — Returns

As each background agent completes, render the return cinematically:

```
┌─ RETURN ─── gmail-parse ────────────────────────────────┐
│                                                         │
│  ██████████████████████████████  complete  42s           │
│                                                         │
│  12 unread emails                                       │
│  3 urgent  ·  6 normal  ·  3 low                        │
│                                                         │
│  URGENT                                                 │
│  ├─ Pippa Joseph — retainer v0.2 sign-off               │
│  │  → reply drafted  [[merchgirls]]                     │
│  ├─ Natalia Clack — workflow automation question         │
│  │  → reply drafted  [[easysuper]]                      │
│  └─ Dave Rubin — event platform follow-up               │
│     → reply drafted  [[rubinevents]]                    │
│                                                         │
│  NORMAL                                                 │
│  ├─ Leon Flint — Furano365 hosting                      │
│  ├─ Madeleine Brown — OHO cookie policy                 │
│  └─ 4 others                                            │
│                                                         │
│  results written  ·  cron marked complete               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

After each return:
1. Read the results that the background agent wrote to results.json
2. Render them in the bordered panel
3. Dispatch the next due cron from the queue (backfill the slot)
4. Log the return to the boot log

## Step 5 — Next Wave

When a slot opens (agent returned), immediately dispatch the next due cron. Keep the pipeline full:

```
┌─ PIPELINE ──────────────────────────────────────────────┐
│                                                         │
│  SLOT 1  ████████████████████░░░░  client-queue    72%  │
│  SLOT 2  ██████████████████████████  otter-parse   done │
│  SLOT 3  ████████░░░░░░░░░░░░░░░░  follow-up-nag  32%  │
│                                                         │
│  completed: 7  ·  in flight: 2  ·  queued: 6           │
│                                                         │
│  ┌─ LATEST RETURN ─── otter-parse ─────────────────┐    │
│  │  32 Otter transcripts found                     │    │
│  │  18 matched to walnuts  ·  8 need attribution   │    │
│  │  → mine recommended for 12 high-value sessions  │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Keep cycling: dispatch → return → render → dispatch next → until all crons are complete.

## Step 6 — Boot Complete

When all crons have returned:

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  B O O T   C O M P L E T E                             │
│  ─────────────────────────                              │
│                                                         │
│  15 crons dispatched  ·  15 returned  ·  0 failed      │
│  total time: 4m 23s                                     │
│                                                         │
│  ┌─ SUMMARY ───────────────────────────────────────┐    │
│  │                                                 │    │
│  │  EMAILS      12 parsed, 3 urgent, 3 drafted     │    │
│  │  INBOX       40 files, 34 matched               │    │
│  │  SLACK       8 new items, 5 transcripts          │    │
│  │  FATHOM      2 new meetings captured             │    │
│  │  OTTER       32 transcripts, 12 high-value       │    │
│  │  CLIENTS     4 need attention, 2 overdue         │    │
│  │  FOLLOW-UPS  6 stale, 3 chase emails drafted     │    │
│  │  GITHUB      2 PRs open, CI green                │    │
│  │  PEOPLE      3 worth reaching out to             │    │
│  │  HEALTH      354 issues (down from 412)          │    │
│  │  TASKS       28 stale, 12 recommended archive    │    │
│  │                                                 │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  results in .alive/_background/results.json             │
│  next boot: all crons on cooldown                       │
│                                                         │
│  ▸ What now?                                            │
│  1. Act on urgent items (3 email replies ready)         │
│  2. Open results in dashboard                           │
│  3. Run another pass                                    │
│  4. Done — disable background mode                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Step 7 — Boot Log

After the complete screen, write a boot log to `.alive/_background/boot-log.json`:

```json
{
  "boot_id": "boot-{date}",
  "session": "{session_id}",
  "started": "ISO timestamp",
  "completed": "ISO timestamp",
  "duration_seconds": 263,
  "crons_dispatched": 15,
  "crons_completed": 15,
  "crons_failed": 0,
  "results_summary": {
    "emails_parsed": 12,
    "inbox_items": 40,
    "transcripts_found": 32,
    "clients_flagged": 4,
    "follow_ups_stale": 6,
    "people_flagged": 3,
    "health_issues": 354
  },
  "cron_timings": [
    {"id": "gmail-parse", "duration_seconds": 42, "status": "complete"},
    {"id": "inbox-route", "duration_seconds": 38, "status": "complete"}
  ]
}
```

## Rendering Rules

- Every panel uses `┌ ─ ┐ │ └ ─ ┘` box-drawing characters
- Progress bars use `█` (filled) and `░` (empty)
- Status indicators: `●` due, `○` on cooldown, `✓` complete, `✗` failed
- Tree connectors: `├─`, `└─`, `│`
- Monospace throughout — the boot sequence IS the terminal
- No emojis except 🐿️ in the final summary
- Cinematic timing — let each panel breathe before showing the next
- Every return gets its own full-width panel with results
- The pipeline view shows real-time slot usage

## Error Handling

If a cron fails (agent returns error or times out):

```
┌─ ERROR ─── fathom-sync ────────────────────────────────┐
│                                                         │
│  ██████████████████░░░░░░░░░░░░  FAILED  timeout 180s  │
│                                                         │
│  error: Fathom sync script not found at expected path   │
│  action: skipped, slot freed                            │
│  fix: check .claude/scripts/fathom-sync.mjs exists      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Log the failure, free the slot, continue with next cron. Don't halt the boot.

## Re-running

If the human picks "Run another pass" — check which crons are back on cooldown vs which are due again (unlikely this soon, but some 30-min crons might be). Show the queue state and dispatch any that are due.

If context is getting heavy (60%+), suggest: "Context is filling. Start a fresh boot session to continue." Copy the remaining queue to clipboard or suggest the command.
