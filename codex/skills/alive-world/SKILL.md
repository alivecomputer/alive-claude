---
name: alive-world
description: "The human doesn't know what to work on, or wants to see everything at once. They need the big picture — what's active, what's stale, what needs attention. Renders a live world view grouped by ALIVE domain, then routes to open, tidy, find, history, or map."
---

# World

This is Mission Control. When the human opens their world, it should feel like booting an operating system — everything they care about, at a glance, with clear paths to action.

NOT a database dump. NOT a flat list. A living view of their world, grouped by what matters, showing relationships, surfacing what needs attention.

---

## Load Sequence

1. **Use the startup orientation appropriately.** `_orientation.json` is a small cached projection that hooks surface automatically when it is valid. It can inform the Attention section, but it is not a complete world listing and must not be treated as a live refresh.
2. **Read `.alive/_index.json` on demand for this world request.** It is the comprehensive local retrieval index: use it to build the tree, identify relevant walnuts, and select any targeted follow-up reads. Do not assume the index is injected into the conversation.
3. **If no index exists** — report that the world needs an explicit refresh. The guaranteed refresh path is an explicit `alive:save`/project operation, which regenerates the index and then the cached orientation. Hooks do not promise a background rebuild. If the user wants to repair a missing index now, run the packaged generator and then read its output. Only on first-time setup, when the generator is unavailable, fall back to a manual scan of walnut keys and projections.
4. Build the tree from the index — parent/child relationships from `parent:` field.
5. **Lightweight fresh checks** — one Bash call each, no subagents, no Explore agents:
   - **Unsaved sessions with stash:** query `recent_sessions` and `stats.unsigned_with_stash` from `_index.json`. If non-zero, surface in the Attention section. No bash loop needed.
   - **Unrouted inputs:** `ls 03_Inbox/ 2>/dev/null | grep -v '^\.' | grep -v '^Icon'` — just the filenames, no deep reads.
   - **API context:** read `.alive/preferences.yaml` only when a relevant configured context source needs to be queried; preferences are not automatically injected.
6. Compute attention items from fresh checks + index staleness signals.
7. **Inbox triage (background)** — if `03_Inbox/` has items, dispatch a background agent to triage them. Don't wait for it — render the dashboard immediately, the triage results arrive while the human reads.

### Inbox Triage Agent

Dispatch with `run_in_background: true` when inbox has 1+ items. The agent:

1. Reads the subagent brief from the plugin templates (for ALIVE context)
2. Lists all files in `03_Inbox/` with `ls -la`
3. For each item, determines:
   - **Type:** transcript, email, document, screenshot, video, extraction directory, financial, unknown
   - **Likely destination walnut:** query relevant `_index.json` entries by keywords, people names, and project names
   - **Priority:** urgent (contains decisions/deadlines), normal, low (reference material)
   - **Age:** how old is the file
4. Returns a structured triage report

When the background agent completes, surface the results:

```
╭─ 🐿️ inbox triaged (8 items)
│
│  Urgent
│   march-expenses.csv              → finance (transactions, needs review)
│   error-log-april-2.txt           → my-startup (build error from deploy)
│
│  Route
│   team-dinner-recap.mp4           → my-startup (event footage)
│   fathom-extraction/              → runs via $alive-mine-for-context
│   otter-extraction/               → runs via $alive-mine-for-context
│
│  Auto-route (low priority)
│   gmail/                          → capture via sync script
│   slack/                          → capture via sync script
│
│  ▸ Route all? Or review one at a time?
│  1. Route all suggested
│  2. Review each
│  3. Skip for now
╰─
```

The triage agent reads only the relevant `_index.json` entries it needs. It matches by name, keywords, and file type patterns. It does NOT move files — it suggests. The human confirms.

**Do not read individual walnut files until the index identifies a reason to do so.** Query `_index.json` for recent sessions and `stats.unsigned_with_stash` before scanning squirrel YAML. The dashboard uses the on-demand index query, cached orientation when available, and the one fast inputs listing; it does not depend on a full index in session context.

## State Detection

Before rendering, detect system state:

- **Fresh install** (no walnuts exist) → route to `setup.md`
- **Previous system detected** (v3/v4 `_brain/` folders exist) → offer migration via `$alive-create-walnut` migrate mode
- **Normal** → render dashboard

---

## Dashboard Layout

The dashboard has 4 sections. Each tells you something different.

### Section 1: Right Now

What needs the human's attention TODAY. Not everything — just what's active and demanding.

```
╭─ 🐿️ your world
│
│  RIGHT NOW
│  ──────────────────────────────────────────────
│
│   1. my-startup              launching
│      Next: Record demo video for investor deck
│      Last: 2 hours ago · 6 sessions this week
│
│   2. freelance-agency        legacy
│      Next: Close out 3 remaining client contracts
│      Last: 2 days ago
│      People: Jake Chen, Sarah Mills
│
│   3. social-content          building
│      Next: Review 8 drafted posts in Buffer
│      ⚠ 4 days past rhythm
│
╰─
```

Only show walnuts that are `active` or past their rhythm. Sort by most recently touched. Show:
- Phase
- Next action (from `_kernel/now.json`)
- Last activity (relative time)
- People involved (from `_kernel/key.md` — max 2-3 names)
- Warning if past rhythm

### Section 2: Attention

Things that need your decision or action. Not walnuts — specific issues.

```
╭─ 🐿️ attention
│
│   → 3 unread emails from Orion (Gmail, 2 days)
│   → Unsaved session on nova-station (squirrel:a3f7, 6 stash items)
│   → 03_Inbox/ has 2 items older than 48 hours
│   → flux-engine quiet for 12 days (rhythm: weekly)
│   → 4 working files older than 30 days across 3 walnuts
│
╰─
```

Sources:
- **Inputs buffer (HIGH PRIORITY)** — anything in `03_Inbox/` older than 48 hours. These are unrouted context that could impact active walnuts TODAY. Stress this to the human: "You have unrouted inputs. These might contain decisions, tasks, or context that affects your active work. Route them before diving into a walnut."
- API context (Gmail unread, Slack mentions, Calendar upcoming)
- Unsaved sessions with stash items (saves: 0)
- Stale walnuts (quiet/waiting)
- Stale working files

**Inputs triage:** The world skill should treat inputs as a buffer — content arrives there and needs routing to its proper walnut. When surfacing inputs, scan the context.manifest.yaml frontmatter (if manifests exist) or the file names to understand what the content might relate to. Don't digest the full content — just flag it, estimate which walnuts it might affect, and urge the human to route it. Use `$alive-capture-context` to process each input properly.

### Section 3: Your World (the tree)

The full structure — grouped by ALIVE domain, with parent/child nesting visible.

```
╭─ 🐿️ your world
│
│  LIFE
│   identity           active     LinkedIn bio update
│   health             quiet      ADHD assessment follow-up
│   finance            quiet      ⚠ 10 days — subscriptions review
│   people/
│     jake-chen        updated 2 days ago
│     sarah-mills      updated 1 day ago
│     tom              updated 5 days ago
│
│  VENTURES
│   my-startup         launching  MVP demo + investor deck
│     └ mobile-app     building   React Native prototype
│   freelance-agency   legacy     Closing out client contracts
│
│  EXPERIMENTS
│   social-content     building   Content calendar + Buffer queue     3 bundles · 4 tasks
│   side-project       waiting    Decide: rewrite or revise
│   podcast            quiet      ⚠ 12 days — episode 4 edit
│   ... +3 more (2 waiting, 1 quiet)
│
│  INBOX
│   2 items (oldest: 4 days)
│
│  ARCHIVE
│   1 walnut (old-portfolio)
│
╰─
```

Key features:
- **Grouped by ALIVE domain** — not a flat list
- **Parent/child nesting** — sub-walnuts indented under parents with `└`
- **People** shown under Life with last-updated
- **Collapse quiet/waiting** — if there are 6+ quiet experiments, show the count not the full list
- **Inputs count** — just how many and how old
- **Archive count** — just the number
- **5-day activity indicator** — `●` dot for each of the last 5 days the walnut was touched. Visual pulse at a glance.

```
│   nova-station          ●●●●● building   Orbital test suite
│   stellarforge       ●●○○○ launching   Relay satellites
│   side-project     ○○○○○ waiting     Decide: rewrite or revise
```

`●` = touched that day. `○` = no activity. Read left to right: today, yesterday, 2 days, 3 days, 4 days. Five dots tells you this walnut is hot. Zero tells you it is cold. No numbers, no dates — just a visual heartbeat.

### Section 4: Recent Squirrel Activity

What's been happening across the world. A pulse check.

Recent session data is in `.alive/_index.json` under `recent_sessions:`. Query it for this view rather than reading individual squirrel YAML files. The index includes squirrel ID, walnut, date, bundle, saves count, summary, and tags for the recent sessions, plus `stats.unsigned_with_stash` for the Attention section.

```
╭─ 🐿️ recent activity
│
│   Today     nova-station         6 sessions · shipped test harness
│   Yesterday nova-station         refined architecture, 22 decisions
│   Feb 22    stellarforge      infrastructure, telemetry, comms
│   Feb 22    nova-station         companion app, integration tests
│   Feb 21    nova-station         module refactor, ecosystem plan
│
│   5 sessions this week · 3 walnuts touched · 47 stash items routed
│
╰─
```

---

## Rendering Rules

1. **Right Now comes first.** Always. It answers "what should I work on?"
2. **Attention is actionable.** Every item should have a clear next step.
3. **The tree is scannable.** Indent sub-walnuts. Collapse where sensible. Show people under Life.
4. **Recent activity gives pulse.** Not details — just "what's been happening."
5. **Numbers for navigation.** Any walnut with a number can be opened by typing the number.
6. **Don't show everything.** Waiting walnuts can be collapsed. Quiet experiments get a count. The human asks for more if they want it.

---

## Index Freshness

`_orientation.json` is a cache produced after `_index.json`; startup hooks render it when present and valid. They do not synchronously crawl the world or regenerate a missing or stale cache. Report that state and offer an explicit refresh.

The guaranteed refresh path is explicit `alive:save`/project work, which regenerates `_index.json` and then `_orientation.json`. Do not claim that background hooks will refresh either file. If the human requests a fresh view outside that path, run the packaged generator on demand:

```bash
python3 "$PLUGIN_ROOT/scripts/generate-index.py" "$WORLD_ROOT"
```

After regenerating, re-read `.alive/_index.json` to render the updated dashboard.

---

## After Dashboard

- **Number** → open that walnut (invoke `$alive-load-context`)
- **"just chat"** → freestyle conversation, no walnut focus
- **"tidy"** → invoke `$alive-system-cleanup`
- **"find X"** → invoke `$alive-search-world`
- **"history"** → invoke `$alive-session-history`
- **"map"** → invoke `$alive-my-context-graph`
- **"mine"** → invoke `$alive-mine-for-context`
- **"open [name]"** → open a specific walnut
- **Attention item** → address it directly ("deal with those emails", "sign that session")

---

## Context Sources (preferences.yaml)

If `context_sources:` is configured in `.alive/preferences.yaml`, surface relevant items from active sources:

- **mcp_live sources** (Gmail, Slack, Calendar, GitHub): Query on demand. Show actionable items only — "3 unread emails from Orion" not "847 emails."
- **sync_script sources**: Check last sync time. If stale, note it.
- **static_export / markdown_vault**: Don't query at dashboard — these are for `$alive-session-history` and `$alive-search-world`.

Filter by walnut scoping — only show sources where `walnuts: all` or the current active walnut is in the list.

---

## Internal Modes

- `setup.md` — first-time world creation (triggers automatically when no ALIVE structure found)
