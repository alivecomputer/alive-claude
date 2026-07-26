---
name: alive-save
description: "The human wants to checkpoint. Or: the stash has grown heavy — 5+ items, 30+ minutes, a natural pause in the work. The agent does not decide when to save. It surfaces the need and lets the human pull the trigger. Runs the full save protocol: confirms stash, writes log, updates state, generates projections, dispatches, resets."
---

# Save

Checkpoint. Route the stash. Update state. Generate projections. Keep working.

Save is NOT a termination. The session continues. Save can happen multiple times. Each save increments the `saves:` counter and updates `last_saved:`. The stop hook only blocks when `saves: 0` (never saved).

---

## Save Flow — Numbered Preconditions

Run each step in order. Do not skip. Do not reorder. Each step lists explicit preconditions and outputs.

### Step 1 — Read existing state (parallel)

Precondition: a walnut is loaded, OR a standalone session needs to be routed.

1. Read `_kernel/now.json` (previous `next:`, active bundle, context)
2. Read `_kernel/log.md` first ~100 lines (recent entries from previous sessions)
3. If `now.json` has a `next.bundle` value, read that bundle's `context.manifest.yaml`
4. Emit one `|` line per file read

Do NOT read task files directly — task data is already in `now.json`. If you need specific task detail, call `tasks.py list --walnut {path}`.

Backward compat: if `_kernel/now.json` is missing, check `_kernel/_generated/now.json`.

Standalone session (no walnut loaded):
1. Ask: "Which walnut does this session belong to?"
2. If the human names one, load its core files and proceed normally
3. If truly walnut-less (system maintenance, cross-walnut, one-off), write the log entry to `.alive/log.md` instead of a walnut log
4. The squirrel YAML at `.alive/_squirrels/` keeps `walnut: null`

This pre-read gives the agent the full picture BEFORE routing — what was expected this session, which bundle was active, what previous sessions accomplished, what task state is. The result: smarter routing, log entries that don't duplicate what's already recorded.

### Step 2 — Pre-Save Scan

1. Ask: "Anything else before I save?"
2. Scan back through messages since last save for stash items that may have been missed
3. Add any new items to the stash list

### Step 3 — Confirm Stash + Next (batched)

1. Render the full stash visually in a single bordered block (see template below)
2. Issue ONE AskUserQuestion call with up to 4 questions — skip empty categories
3. Insight candidates require a separate AskUserQuestion call (different decision shape)

**Stash display template:**
```
╭─ 🐿️ save checkpoint
│
│  decisions (3)
│   1. Orbital test window confirmed for March 4  → nova-station
│   2. Ryn's team handles all telemetry review  → nova-station
│   3. Festival submission over gallery showing  → glass-cathedral
│
│  tasks (2)
│   4. Book ground control sim for Feb 28  → nova-station
│   5. Submit festival application by Mar 1  → glass-cathedral
│
│  notes (1)
│   6. Jax mentioned new radiation shielding vendor  → [[jax-stellara]]
│
│  next: was "Review telemetry from test window"
╰─
```

**Question slots (skip empty categories):**

| Slot | Category | Options |
|---|---|---|
| 1 | Decisions | "Confirm all" / "Review list" / "Drop some" |
| 2 | Tasks | "Confirm all" / "Edit or drop" |
| 3 | Notes | "Confirm all" / "Drop some" |
| 4 | Previous next: | "Completed" / "Move to tasks, new next" / "Still the priority" |

Every question supports "Other" for free-text elaboration — editing items, adding context, changing routing, explaining what happened.

**Insight candidate question (separate call, only if any exist):**

```
╭─ 🐿️ insight candidate
│   "Orbital test windows only available Tue-Thu due to
│    ISS scheduling conflicts"
│
│   Commit as evergreen insight, or just log it?
╰─
```

→ AskUserQuestion: "Commit as evergreen" / "Just log it"

If the previous `next:` was NOT completed and is being replaced, route it as a task via `tasks.py add` to the relevant bundle with context.

### Step 4 — Write Log Entry (must come before any other write)

Precondition: stash confirmed in Step 3.

1. Prepend a signed entry to `_kernel/log.md` using the standard template
2. The entry must include:
   - What happened (brief narrative)
   - Decisions made (with rationale — WHY, not just WHAT)
   - Tasks created or completed
   - References captured
   - Next actions identified

The log is truth. Everything else derives from it. The log entry MUST be written BEFORE any other file in this flow.

### Step 5 — Prepare Remaining Content (in memory)

1. Re-read `_kernel/log.md` first ~150 lines to ground remaining work in the actual written log (this captures the entry just prepended in Step 4 plus the previous 3-4 entries)
2. Prepare content for all remaining files in memory:
   - Active bundle's `context.manifest.yaml` — update `context:` field, merging new info with existing context (do not flatten rich context from a previous deep session)
   - `_kernel/insights.md` — new evergreen entries (only if confirmed in Step 3)
   - Cross-walnut dispatches — brief log entries for destination walnuts
   - Tasks via `tasks.py` — plan the calls:
     - New task: `python3 "${PLUGIN_ROOT}/scripts/tasks.py" add --walnut {path} --title "..." --bundle {name} --priority urgent`
     - Mark done: `python3 "${PLUGIN_ROOT}/scripts/tasks.py" done --walnut {path} --id t001`
     - Modify: `python3 "${PLUGIN_ROOT}/scripts/tasks.py" edit --walnut {path} --id t001 --priority active`

The agent does NOT write `now.json` directly. The explicit save workflow runs the packaged projector after all source and task writes, so it assembles `now.json` from the completed source state. Post-write hooks may duplicate this best-effort, but they do not define save completion.

### Step 6 — Write Remaining Files (parallel)

Precondition: Step 4 complete (log entry written) and Step 5 complete (content prepared).

Fire all remaining writes as parallel calls in a single message:
- Active bundle's `context.manifest.yaml` — context field update via `apply_patch`
- `_kernel/insights.md` — new evergreen entries via `apply_patch` (if any confirmed)
- Cross-walnut dispatches — brief log entries to destination walnut logs via `apply_patch` (if any)
- Cross-walnut task additions — tasks routed to other walnuts via `tasks.py` (if any)
- Tasks via `tasks.py` Bash calls — can run in parallel with the file writes above

These are independent of each other — they only depend on the log entry existing.

### Step 7 — Update Squirrel Entry

Precondition: Step 6 complete.

1. Read the current YAML at `.alive/_squirrels/{session_id}.yaml`
2. Use `apply_patch` to update:
   - `walnut:` — set to the active walnut name (or keep `null` if no walnut opened)
   - `stash:` — replace `[]` with routed items, tagged by type and destination
   - `working:` — list any working files created or modified this session
   - `saves:` — increment by 1 (was 0 on first save, 1 on second, etc.)
   - `last_saved:` — set to current ISO timestamp

Stash format:
```yaml
stash:
  - content: "Orbital test window confirmed for March 4"
    type: decision
    routed: nova-station
  - content: "Book ground control sim for Feb 28"
    type: task
    routed: nova-station
  - content: "Jax mentioned new radiation shielding vendor"
    type: note
    routed: jax-stellara
```

This is cumulative across saves. Each save APPENDS new items to `stash:`, it does not replace. The YAML becomes the full record of everything routed during the session.

### Step 8 — Route New Walnuts (only if needed)

Precondition: any stash items require scaffolding new walnuts (new person, new venture/experiment).

These are heavier operations and may need their own confirmation. Run AFTER the parallel writes in Step 6.

- New person → scaffold person walnut in `02_Life/people/`
- New venture/experiment → scaffold walnut with `_kernel/`

Legacy person walnuts at `02_Life/people/` are still recognized.

### Step 9 — Refresh projections, index, and orientation

Precondition: all source, bundle, and task writes are complete.

Run the packaged save-refresh command after every explicit save. For an active
walnut it runs `project.py --walnut`, then the world index and orientation
refresh. For a standalone/no-walnut save, omit `--walnut`: it deliberately
skips `project.py` and still refreshes the world index and orientation.

```bash
python3 "$PLUGIN_ROOT/scripts/save-refresh.py" --world "$WORLD_ROOT" --walnut "{path}"
# Standalone/no-walnut save:
python3 "$PLUGIN_ROOT/scripts/save-refresh.py" --world "$WORLD_ROOT"
```

`save-refresh.py` runs `project.py --walnut` when supplied, then
`generate-index.py WORLD_ROOT`, explicitly runs `orientation.py build
WORLD_ROOT`, and verifies the fresh, strict schema-1 `_orientation.json` cache
renders.
If any command or verification fails, the save is not fully complete: report
that source checkpoint persistence may be recorded but projection refresh is
incomplete, preserve source writes for repair, and do not announce the
checkpoint as fully saved. Hooks may run the same work as best-effort
duplication, but they are not the completion guarantee.

### Step 10 — Integrity Check

Walk the checklist. Fix anything that fails before completing the save.

- [ ] **now.json** — packaged `project.py --walnut` completed from the log entry and source files. Verify the log entry has enough context for a good projection.
- [ ] **Log entry** — does it capture WHY decisions were made, not just WHAT?
- [ ] **Tasks** — were tasks routed via `tasks.py`? Verify by calling `tasks.py list --walnut {path}` if uncertain.
- [ ] **Bundles** — was any bundle worked on this session? Is its manifest updated (sources, decisions, status)?
- [ ] **References** — was any external content discussed this session that wasn't captured? Any research worth saving? Route to bundle `raw/` if active bundle exists.
- [ ] **Insights** — did any standing domain knowledge surface that should be proposed as evergreen?
- [ ] **People** — was anyone mentioned who should have context dispatched to their walnut?
- [ ] **Bundle status** — should any bundle advance? (draft → prototype when it has a visual; prototype → published when shared externally; published → done when outputs graduated). Graduation is a status flip in the manifest.
- [ ] **Bundle shared** — was a bundle shared with someone this session? If so, update the manifest's `shared:` frontmatter (to, method, date, version) and stash a dispatch to the person's walnut.

Post-save note: post-write hooks can independently run `project.py` and `generate-index.py` for observed local writes, but hosted and specialized paths may bypass them. The explicit Step 9 commands are the save-completion boundary.

### Step 11 — Continue

Session continues. Stash resets for next checkpoint.

```
╭─ 🐿️ saved — checkpoint 2
│  3 decisions routed to log
│  2 tasks added via tasks.py
│  1 dispatch to [[jax-stellara]]
│  next: updated
│  zero-context: ✓
│
│  Run $alive-system-cleanup? (stale walnuts, orphan refs, stale drafts)
╰─
```

The check suggestion is lightweight — one line. If the human ignores it, no friction. If they say "check" or "yeah", invoke `$alive-system-cleanup`.

---

## On Actual Session Exit

When the session truly ends (stop hook, explicit "I'm done done", the human leaves):

1. Update the squirrel entry in `.alive/_squirrels/{session_id}.yaml`:
   - Set `ended:` to current timestamp
   - `saves:` is already > 0 from the last save
   - Set `transcript_path:` — scan `~/.claude/projects/*/` for a JSONL file containing the session ID
2. The entry is already saved — this step adds the exit metadata

---

## Empty Save

If nothing was stashed since last save — skip the ceremony.

```
╭─ 🐿️ nothing to save since last checkpoint.
╰─
```
