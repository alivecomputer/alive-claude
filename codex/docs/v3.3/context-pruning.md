# Context Pruning and Retrieval v3.3

## Principle

Pruning means moving detail out of the default orientation pack while keeping
it addressable and attributable. It must not silently delete history, raw
references, confirmed insights, or completed-task evidence.

## Context budgets

Add configurable byte and approximate-token budgets:

```yaml
context_budget:
  orientation_tokens: 6000
  now_bytes: 32768
  recent_log_entries: 12
  recent_sessions: 8
  active_bundles_full: 3
  inactive_bundles_summary: 20
  search_file_bytes: 524288
```

The shipped Codex runtime keeps `_index.json` as the comprehensive local
retrieval index. Codex-only callers explicitly opt into a compact
`_orientation.json` build; the shared generator's default invocation updates
only the index pair. The cache is schema version 1, capped at 8,192 bytes, and
contains at most nine recommendations; Codex startup hooks render at most
three. Hooks only read the cached orientation and source-index stat identity.
They emit a short bounded health notice for a missing, invalid, unsupported,
or stale cache rather than crawling the world or reading the full index during
startup.

An explicit save/project path is the guaranteed refresh: `save-refresh.py`
projects an active walnut when present, regenerates the index, explicitly
rebuilds orientation, and verifies its fresh strict schema-1 cache renders.
For a standalone save it skips walnut projection but still refreshes the world
cache. Background hooks are not a refresh guarantee. World and search requests
query `_index.json` on demand and use targeted source reads when detail is
needed.

## Lifecycle rules

- Chapter `log.md` at a phase boundary or 50 entries into
  `_kernel/history/chapter-NN.md`; leave signed summaries and date ranges.
- Move superseded but still valid insights to dated insight archives with
  backlinks; never discard confirmed standing knowledge silently.
- Expire session `working` lists and plugin recovery records after a successful
  save plus retention window.
- Move completed tasks to `completed.json` with completion time, evidence, and
  original source/session.
- Summarize inactive bundles in `now.json`; load their manifest or raw sources
  only on demand.
- Exclude `.git`, worktrees, conflicts, `node_modules`, `.venv`, build outputs,
  caches, `.wrangler`, binaries, and cloud placeholders from default scans.
- Report oversized files and unreadable/dataless placeholders rather than
  blocking indefinitely.

## Doctor output

The installed `doctor.sh --world PATH` validates the strict schema-1 cache,
shared YAML/JSON generation marker, source generation, full index digest, size,
and modification identity. It also rejects installed skills that claim the
full world index is injected and follows registered Codex hook dependencies.

This is not a Claude pruning claim. Claude hook files and their legacy
full-index/context injection behavior were left unchanged pending dedicated
evals.

The broader proposed `alive doctor context --walnut PATH` work remains
unshipped. It should report:

- orientation bytes/tokens by source;
- log entries and chapter recommendation;
- active/inactive bundle counts;
- oversized or malformed JSON/frontmatter;
- orphan tasks, stale sessions, and unsigned entries;
- caches/worktrees accidentally inside walnut scan scope;
- raw references missing from manifests;
- recoverable pruning commands, all dry-run by default.

## Retrieval invariant

Every summary carries source paths and date/session ranges. Search spans active
log plus chapters and returns the source location. A zero-context agent can
reconstruct why a summary exists without loading the entire historical log.
