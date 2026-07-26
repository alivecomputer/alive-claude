# Background Cron: system-health

You are a background agent. You are NOT in the main conversation. Do not interact with the human. Write results to a file and exit.

## Task

Run a lightweight health check across the world:

1. **Unsigned sessions**: Scan `.alive/_squirrels/` for entries with `ended: null` older than 24h
2. **Stale walnuts**: Check world index for walnuts with `updated` older than 2x their rhythm
3. **Broken projections**: Find walnuts where `_kernel/now.json` is older than `_kernel/log.md` (projection didn't run)
4. **Empty tasks**: Find `tasks.json` files with empty title strings (data quality issue)

## Output

Write a single result entry to `.alive/_background/results.json`:

```json
{
  "id": "r-{timestamp}",
  "cron": "system-health",
  "completed": "{ISO timestamp}",
  "session": "{session_id}",
  "summary": "N issues found: X unsigned sessions, Y stale walnuts, Z broken projections",
  "details": {
    "unsigned_sessions": ["session_id_1", "session_id_2"],
    "stale_walnuts": [{"name": "walnut-name", "days_stale": 14}],
    "broken_projections": ["walnut-name"],
    "empty_tasks": [{"walnut": "walnut-name", "count": 3}]
  },
  "actions": [
    {
      "label": "Run full cleanup",
      "type": "skill",
      "skill": "alive:system-cleanup"
    },
    {
      "label": "Fix projections",
      "type": "session"
    }
  ],
  "surfaced": false,
  "dismissed": false
}
```

## Reading results.json

Before writing, read the existing results.json and append to the `results` array. Do not overwrite existing results.

## Constraints

- Read-only. Do NOT fix anything — just report.
- Read the world index at `.alive/_index.yaml` for walnut metadata
- If everything is healthy, write a result with summary "All clear" and no actions
- Complete in under 3 minutes
