---
name: alive-search-world
description: "The human needs something that exists somewhere in the world but they don't know where. A decision, a person, a file, a reference — it's been captured, they just can't find it. Searches decisions, people, files, references, insights, and log history across all walnuts in priority order."
---

# Find

Search across the world. One verb for all retrieval.

---

## How It Searches

Priority order — fastest and highest signal first:

### 1. Index Query (fast, structured)
Read or query `.alive/_index.json` only for this search request. It identifies likely walnuts, people, tags, links, and recent session references before any targeted file reads. `_orientation.json` is a startup cache for short recommendations, not a search corpus.

### 2. Frontmatter Scan (targeted)
Scan `_kernel/key.md` only in walnuts selected by the index query. Matches on: type, goal, people names, tags, links, reference descriptions.

### 3. Insights Search (standing knowledge)
Scan `_kernel/insights.md` across relevant walnuts. Domain knowledge that persists — "Nova Station test windows are Tue-Thu only."

### 4. Log Search (decisions, history)
Search `_kernel/log.md` entries. Signed decisions, session summaries, what happened when. Frontmatter first (last-entry, summary), then entry bodies.

### 5. Task Search (work queue)
Use `tasks.py list` to query tasks across walnuts. Find tasks by status, age, attribution.

### 6. Working File Search (drafts)
Scan `*/` across walnuts (bundles are flat in walnut root). Find drafts by name, version, age, squirrel attribution.

### 7. Bundle Manifest Search (captured content metadata)
Search `*/context.manifest.yaml` files across walnuts (bundles are flat in walnut root). Match on frontmatter: type, date, source, participants, subject.

### 8. Raw Reference Search (expensive)
Load actual raw files. Only on explicit request — "read me that email from Jax."

### 9. Context Source Cascade (if nothing found locally)
**If steps 1-8 return nothing and the user believes it exists**, read `.alive/preferences.yaml` and fan out to configured context sources before reporting "not found." Preferences and connections are not automatically injected at startup.

One-hop inference applies: if the user says "the setup guide I sent Sarah" and an email integration is configured, that's enough to trigger a search without being asked. The system should resolve across its full context surface — local files are not the only source of truth.

```
╭─ 🐿️ not found in local files
│  Checking configured context sources...
│  → Found in email: sent to Sarah, Mar 15, "Setup Guide v2"
│
│  ▸ What now?
│  1. Read it
│  2. Capture it to a walnut
│  3. Skip
╰─
```

**Never say "not found" if context sources haven't been checked.**

## Cache Freshness Boundary

Hooks can surface a cached `_orientation.json` at startup, but they do not guarantee a background refresh. A stale or missing orientation is reported rather than regenerated during startup. The explicit `alive:save`/project path is the guaranteed way to regenerate `_index.json` and `_orientation.json`; search uses the index on demand and may tell the human when it is stale.

---

## Cross-Walnut Search

Find searches across ALL walnuts by default. Results show which walnut each match came from.

```
╭─ 🐿️ found 3 matches for "radiation shielding"
│
│   1. nova-station / insights.md
│      "Ceramic composites outperform aluminum at 3x the cost"
│
│   2. nova-station / _kernel/log.md — 2026-02-23
│      Decision: go with hybrid shielding approach
│
│   3. nova-station / research/
│      2026-02-23-radiation-shielding-options.md
│
│  number to load, or refine search.
╰─
```

## Connections

When a match is found, surface connected walnuts:

```
╭─ 🐿️ [[ryn-okata]] is mentioned in this entry.
│  She also appears in: nova-station, glass-cathedral
│  Load her context?
╰─
```

## Temporal Queries

"What happened last week" → filter log entries by date range, show across all active walnuts.

"What changed since Tuesday" → scan `_kernel/now.json` updated timestamps + recent log entries.

"History of nova-station" → show `_kernel/log.md` frontmatter (entry count, summary) + offer to load recent entries.
