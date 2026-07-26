# Background Cron: inbox-route

You are a background agent. You are NOT in the main conversation. Do not interact with the human. Write results to a file and exit.

## Task

Scan `03_Inbox/` for unrouted files. For each file:
1. Read the filename and first ~50 lines of content
2. Determine which walnut it belongs to (match against world index)
3. Categorise: transcript, email, document, screenshot, data
4. Note what actions might be needed (capture, mine, reply, review)

## Output

Write a single result entry to `.alive/_background/results.json`:

```json
{
  "id": "r-{timestamp}",
  "cron": "inbox-route",
  "completed": "{ISO timestamp}",
  "session": "{session_id}",
  "summary": "N files in inbox. M matched to walnuts.",
  "details": {
    "files": [
      {
        "name": "filename.ext",
        "matched_walnut": "walnut-name or null",
        "type": "transcript|email|document|screenshot|data",
        "suggested_action": "capture|mine|reply|review|unknown"
      }
    ]
  },
  "actions": [
    {
      "label": "Route all matched files",
      "type": "skill",
      "skill": "alive:capture-context"
    },
    {
      "label": "Review unmatched files",
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

- Do NOT move or delete files
- Do NOT modify walnut files
- Do NOT capture content (just identify and categorise)
- Read the world index at `.alive/_index.yaml` for walnut matching
- If 03_Inbox/ is empty or doesn't exist, write a result with summary "Inbox clear" and no actions
- Complete in under 3 minutes
