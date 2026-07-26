# Tasks and Commitments v3.3

## Current evidence

Real-world sampling found mixed generations of tasks: some use `title`, others
legacy `text`; most have status/priority, but due dates, assignees, completion
criteria, dependencies, and update timestamps are sparse. A v3.3 change must
normalize without requiring every walnut to migrate at once.

## Additive task fields

```json
{
  "id": "world_7f3c:04_Ventures/example:t0042",
  "title": "Send revised proposal",
  "status": "waiting",
  "priority": "active",
  "kind": "commitment",
  "direction": "outbound",
  "counterparty": "[[alex-example]]",
  "source_ref": "log:2026-07-21T09:30:00Z",
  "created": "2026-07-21T09:30:00Z",
  "updated": "2026-07-21T09:31:00Z",
  "due": "2026-07-23",
  "review_at": "2026-07-22",
  "blocked_by": ["world_7f3c:04_Ventures/example:t0038"],
  "done_when": "Alex confirms the commercial terms",
  "recurrence": null,
  "session": "019f..."
}
```

All new fields are optional. Readers accept legacy `text` as `title`; writers
emit `title` and preserve unknown fields. Existing local numeric IDs remain
valid, while world-qualified IDs are added when tasks cross walnut or sync
boundaries.

## Status model

- `todo`: accepted but not active.
- `active`: currently actionable.
- `waiting`: another person/event owns the next movement; requires
  `counterparty` or `blocked_by` and a `review_at` date.
- `scheduled`: intentionally deferred until a date/time.
- `blocked`: cannot proceed and needs an explicit blocker.
- `done`: completion evidence is recorded.
- `dropped`: intentionally abandoned with reason.

Priority and status remain separate. “Urgent” is priority, not workflow state.

## Commands

Extend `tasks.py` with normalization-first commands:

```text
tasks.py doctor --walnut PATH
tasks.py normalize --walnut PATH --dry-run
tasks.py wait --id ID --counterparty REF --review-at DATE
tasks.py schedule --id ID --at DATE
tasks.py block --id ID --by ID --reason TEXT
tasks.py review --walnut PATH --before DATE
```

Every mutation updates `updated`, records session/origin, writes atomically, and
can be reconstructed from the prepend-only log. `normalize --dry-run` shows the
exact JSON diff and never discards unknown keys.

## Commitment views

Project separate views from the same task records:

- **I owe:** outbound commitments by counterparty and due/review date.
- **Owed to me:** inbound commitments awaiting another party.
- **Waiting:** tasks with the next review moment.
- **Unowned:** active tasks without a responsible actor.
- **Unclear completion:** tasks missing `done_when` above a configurable age.
