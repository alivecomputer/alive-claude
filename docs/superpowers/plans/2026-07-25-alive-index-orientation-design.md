# ALIVE Index Integrity and Bounded Orientation Design

**Status:** Implemented with a Codex-only release-boundary amendment
**Date:** 2026-07-25
**Target:** ALIVE v3.3 private alpha, beginning with `3.3.0-alpha.3`

**Release-boundary amendment (2026-07-25):** The bounded orientation lifecycle
is enabled only by Codex in alpha.3. The shared generator builds orientation
only with the explicit Codex `--build-orientation` flag. Claude hook files
remain byte-identical to baseline `c9d6d7e`, including their legacy full-index
and broader-context injection behavior. Changing that behavior is deferred
until a separate Claude evaluation provides evidence for the change.

## Decision

ALIVE will stop treating the complete world index as session-start context.
The comprehensive index remains a local, generated retrieval surface. A new
bounded orientation projection becomes the only world-wide projection that
the Codex adapter may inject automatically. Other adapters may adopt it only
after adapter-specific evaluation.

Index correctness and bounded orientation ship before the broader typed-task
and commitment model. Recommendations may classify legacy tasks in the first
release, but task mutation semantics remain a separate implementation plan.

## Evidence

The real test world exposed two independent failures:

- `.alive/_index.yaml` was 64,588 bytes (about 16,000 tokens) and invalid YAML.
- The shared generator parsed a multiline squirrel `tags:` list with a regex
  whose `\s*` crossed the newline, turning `- supernormal-winddown` into a
  scalar. The handwritten emitter then produced the invalid flow value
  `tags: [- supernormal-winddown]`.
- `.alive/_index.json` remained syntactically valid but preserved the wrong
  semantic value `["- supernormal-winddown"]`.
- The legacy Claude session hook injected the entire YAML index. The Codex
  v3.3 hook did not inject it, while the Codex `alive-world` skill incorrectly
  claimed that it did.
- The active world contained 1,188 open tasks, including definite temporal and
  state defects. Injecting that inventory would make orientation less useful,
  not more useful.

The defect is shared-runtime code, not a Codex-only file problem.

## Product Behaviour

At session start ALIVE may say:

> ALIVE found 9 things needing attention: 3 I can do now, 2 commitments at
> risk, 1 likely reply owed, and 3 records needing review. Your requested work
> still comes first.

Only the top three recommendations appear automatically. The user can ask to
show all, run a safe action, review an item, dismiss it, or continue their
original task. Orientation never performs a mutation.

## Data Surfaces

### `.alive/_index.json`

The comprehensive, machine-readable world index:

- all recognized walnuts and people;
- paths, types, goals, phases, links and bundle summaries;
- generated metadata and counts;
- recent session summaries needed for retrieval.

It is generated locally and queried on demand by Codex. Codex never injects it
wholesale into a session. The unchanged Claude baseline remains an explicit
exception pending its separate lifecycle evaluation.

### `.alive/_index.yaml`

A JSON-compatible YAML generated view. It is not a canonical machine input
and Codex never injects it automatically. The unchanged Claude baseline may
still inject it. Dynamic values must be serialized safely. Generation must not
replace the last valid file with invalid output.

### `.alive/_orientation.json`

A bounded projection with this contract:

```json
{
  "schema_version": 1,
  "generated": "2026-07-25T05:00:00Z",
  "world": {
    "root": "/path/to/world",
    "walnuts": 71,
    "people": 207,
    "unrouted_inputs": 59
  },
  "health": {
    "index_valid": true,
    "projection_stale": false,
    "issue_count": 9
  },
  "recommendations": [
    {
      "id": "task:walnut-world:t008:expired-relative-date",
      "kind": "expired_relative_date",
      "severity": "warning",
      "confidence": "high",
      "walnut": "walnut-world",
      "task_id": "t008",
      "summary": "\"tomorrow\" is 72 days old",
      "evidence": {
        "path": "04_Ventures/example/_kernel/tasks.json",
        "created": "2026-05-14",
        "status": "todo"
      },
      "proposed_action": "review_task",
      "can_run_now": false
    }
  ],
  "counts": {
    "total_detected": 9,
    "shown": 3
  }
}
```

Constraints:

- maximum serialized size: 8,192 bytes;
- maximum stored recommendations: 9;
- maximum automatically rendered recommendations: 3;
- evidence paths are world-relative;
- no task bodies, source contents, credentials or raw private material;
- deterministic ordering by severity, confidence, temporal urgency, then ID;
- truncation removes whole recommendation objects, never bytes from JSON.

## Initial Recommendation Rules

The first version detects only high-confidence, deterministic exceptions:

1. Open task with an elapsed relative-date term such as `today`, `tomorrow`,
   `this weekend`, `next week`, or a named weekday, anchored to `created`.
2. Open task with a `due` date before the current date.
3. Title says blocked/waiting while formal status is `todo` or `active`.
4. Title says complete/done/shipped/cancelled while formal status remains open.
5. Urgent task missing both assignee and due date.
6. Generated index invalid, missing, or older than its source projection.

Age alone does not classify a task as dead. Old tasks may be surfaced as a
count, but they are not recommended for deletion or completion automatically.

## Runtime Flow

1. Post-save projection regenerates `now.json`.
2. Index generation writes candidate JSON and YAML files into the destination
   directory.
3. The generator validates its structured payload and safe-output invariants.
4. Valid candidates atomically replace the previous index files.
5. Codex explicitly opts into orientation generation, which consumes
   `_index.json` plus structured task files and atomically writes
   `_orientation.json`. The shared generator's default invocation does not.
6. Codex session-start and resume hooks read only `_orientation.json`, enforce
   the byte limit, and render a bounded summary.
7. `alive-world`, `alive-search-world`, MCP and UI consumers query the complete
   JSON index only when the user asks for world-wide retrieval.

Startup does not synchronously crawl the full world. If orientation is absent
or stale, the hook reports that fact and continues with the user’s task.

## Cross-Runtime Contract

The orientation JSON contract is shareable across adapters, but alpha.3
enables it only in Codex:

- Codex hooks can inject the cached bounded summary.
- Claude retains its legacy hook behavior pending a separate evaluation; no
  bounded-orientation parity is claimed.
- No runtime may claim guaranteed background detection from best-effort hooks.
- Explicit save/project commands remain the guaranteed refresh path.
- MCP exposes read-only orientation and index queries; mutations continue
  through explicit ALIVE task and save operations.

## Privacy and Failure Behaviour

- All indexing and orientation computation is local by default.
- No index or orientation data is sent to OpenAI, Anthropic or an ALIVE service
  by the generator.
- Context added by a host lifecycle hook becomes model input and may be sent to
  the provider configured for that host unless the user uses a local transport.
- Failed generation preserves the last valid projection.
- A malformed source becomes a health recommendation with a source-relative
  path; generation does not silently skip it without recording the issue.
- Hooks fail open: ALIVE context assistance may be absent, but the host session
  remains usable.

## Typed Tasks Follow-Up

The next plan will extend task records without breaking legacy tasks. At
minimum it will distinguish:

- `human_action`;
- `commitment` with direction, counterparty and evidence;
- `implied_follow_up`;
- `agent_step`;
- `consideration`.

Orientation will then group recommendations by what the agent can execute,
what the human owes, what another party owes, what needs review, and what is
only an idea.

## Acceptance Criteria

- The real multiline squirrel tag fixture produces valid YAML and the exact
  JSON tags `["supernormal-winddown", "patrick-super", "sgc"]`.
- Generator failure cannot overwrite a valid existing index.
- Codex startup injects neither `_index.yaml` nor `_index.json`.
- Codex-injected orientation is no larger than 8,192 bytes and contains at
  most three rendered recommendations.
- Claude hook behavior remains unchanged and is documented as a release gap
  until its dedicated evaluation passes.
- The known `tomorrow`, overdue, blocked/status and complete/status fixtures
  produce deterministic recommendations.
- A 60-day-old task with no other defect is not called dead.
- Existing clean install, upgrade, uninstall, hook, MCP and real-walnut
  recovery tests remain green.
