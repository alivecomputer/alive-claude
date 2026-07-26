# ALIVE Index Integrity and Bounded Orientation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared ALIVE index safe and atomic, replace Codex full-index
prompt assumptions with a bounded cached orientation, and surface deterministic
recommended actions in the Codex adapter.

**Architecture:** Keep `_index.json` as the comprehensive local retrieval index
and write the same JSON-compatible YAML data to `_index.yaml`. Add a
zero-dependency `orientation.py` projection that Codex explicitly requests
with `--build-orientation`; Codex startup hooks render only this bounded cached
projection and never crawl the world.

**Tech Stack:** Python 3 standard library, POSIX shell hooks, `unittest`, JSON, generated YAML subset, existing ALIVE shared-runtime sync.

> **Release-boundary amendment (2026-07-25):** Instructions below that proposed
> default orientation generation or Claude hook changes are superseded by this
> amendment. Default shared-generator invocation creates only the index pair;
> the Codex post-write path passes `--build-orientation`. Claude hooks and
> `plugins/alive/tests/test_orientation_hooks.py` remain byte-identical to
> baseline `c9d6d7e`. No Claude change is authorized without separate eval
> evidence.

## Global Constraints

- Preserve the existing ALIVE v3 architecture and shared walnut format.
- Add no runtime dependency such as PyYAML.
- Maximum `_orientation.json` size is 8,192 bytes.
- Store at most 9 recommendations and automatically render at most 3.
- Age alone never marks a task dead, done, dropped, or safe to delete.
- Orientation is read-only; all mutations require explicit user approval and existing ALIVE operations.
- Generated writes are atomic and preserve the previous valid projection on failure.
- Startup must not synchronously crawl the world.
- Index and orientation generation and storage remain local. Context added by
  a trusted lifecycle hook may be sent to the provider configured for that
  host unless the user uses a local transport.

---

### Task 1: Reproduce and Fix Shared Index Serialization

**Files:**
- Create: `codex/tests/test_index_generation.py`
- Modify: `plugins/alive/scripts/generate-index.py`
- Synchronize: `codex/scripts/generate-index.py`

**Interfaces:**
- Consumes: world directory containing `.alive/_squirrels/*.yaml`.
- Produces: `extract_yaml_list(content: str, field: str) -> list[str]`, safe YAML list output, atomic `_index.yaml` and `_index.json`.

- [ ] **Step 1: Write the failing multiline-tag regression test**

```python
def test_multiline_squirrel_tags_are_preserved_without_leading_dash(self):
    squirrel = self.world / ".alive" / "_squirrels" / "session.yaml"
    squirrel.write_text(
        "session_id: session-123\n"
        "walnut: demo\n"
        "started: 2026-07-25T01:00:00Z\n"
        "saves: 2\n"
        "tags:\n"
        "  - supernormal-winddown\n"
        "  - patrick-super\n"
        "  - sgc\n",
        encoding="utf-8",
    )
    result = self.run_generator()
    self.assertEqual(0, result.returncode, result.stderr)
    payload = json.loads((self.world / ".alive" / "_index.json").read_text())
    self.assertEqual(
        ["supernormal-winddown", "patrick-super", "sgc"],
        payload["recent_sessions"][0]["tags"],
    )
    yaml_text = (self.world / ".alive" / "_index.yaml").read_text()
    self.assertIn(
        "tags: [supernormal-winddown, patrick-super, sgc]", yaml_text
    )
    self.assertNotIn("tags: [- supernormal-winddown]", yaml_text)
```

- [ ] **Step 2: Write failing escaping and previous-file-preservation tests**

```python
def test_generated_lists_quote_yaml_sensitive_values(self):
    self.write_squirrel(tags=["needs:review", "-leading", "quoted \"value\""])
    self.assertEqual(0, self.run_generator().returncode)
    text = (self.world / ".alive" / "_index.yaml").read_text()
    self.assertIn('"needs:review"', text)
    self.assertIn('"-leading"', text)
    self.assertIn('"quoted \\\\"value\\\\""', text)

def test_failed_generation_preserves_previous_indexes(self):
    alive = self.world / ".alive"
    (alive / "_index.json").write_text('{"sentinel": true}\\n')
    (alive / "_index.yaml").write_text("sentinel: true\\n")
    result = self.run_generator(extra_env={"ALIVE_INDEX_TEST_FAIL": "1"})
    self.assertNotEqual(0, result.returncode)
    self.assertEqual('{"sentinel": true}\\n', (alive / "_index.json").read_text())
    self.assertEqual("sentinel: true\\n", (alive / "_index.yaml").read_text())
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
python3 -m unittest codex.tests.test_index_generation -v
```

Expected: failures showing the leading dash in JSON/YAML and non-atomic direct writes.

- [ ] **Step 4: Implement explicit multiline list parsing**

Add to `plugins/alive/scripts/generate-index.py`:

```python
def extract_yaml_list(content, field):
    lines = content.splitlines()
    marker = re.compile(r"^" + re.escape(field) + r":[ \t]*(?:\\[\\])?[ \t]*$")
    item = re.compile(r"^[ \t]+-[ \t]+(.*)$")
    for index, line in enumerate(lines):
        if not marker.match(line):
            continue
        values = []
        for following in lines[index + 1:]:
            matched = item.match(following)
            if matched:
                values.append(matched.group(1).strip().strip("\"'"))
                continue
            if following.startswith((" ", "\\t")) or not following.strip():
                continue
            break
        return values
    return []
```

Change scalar matching from `\s*` to `[ \t]*`, and obtain tags with:

```python
tags_list = extract_yaml_list(sq_content, "tags")
if not tags_list:
    tags_list = parse_inline_list(extract_sq_field(sq_content, "tags"))
```

- [ ] **Step 5: Route recent-session tags through the shared safe list serializer**

Replace:

```python
tags_str = ", ".join(rs["tags"])
lines.append(f"    tags: [{tags_str}]")
```

with:

```python
lines.append(f'    tags: {yaml_list(rs["tags"])}')
```

- [ ] **Step 6: Add an atomic text writer and use it for both indexes**

```python
def atomic_write_text(path, text):
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary_name, destination)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
```

Build both serialized candidates before either replacement. Keep the
`ALIVE_INDEX_TEST_FAIL` branch immediately before replacements so the
preservation test exercises the failure boundary.

- [ ] **Step 7: Run the focused tests and verify they pass**

Run:

```bash
python3 -m unittest codex.tests.test_index_generation -v
```

Expected: all index generation tests pass.

- [ ] **Step 8: Synchronize the allowlisted shared runtime and verify no drift**

Run:

```bash
python3 codex/scripts/sync_shared_runtime.py \
  --source-root plugins/alive \
  --plugin-root codex \
  --manifest codex/shared-runtime.json
python3 codex/scripts/sync_shared_runtime.py \
  --source-root plugins/alive \
  --plugin-root codex \
  --manifest codex/shared-runtime.json \
  --check
```

Expected: second command prints `{"divergent": []}`.

- [ ] **Step 9: Commit the serialization fix**

```bash
git add plugins/alive/scripts/generate-index.py \
  codex/scripts/generate-index.py \
  codex/tests/test_index_generation.py
git commit -m "fix: make ALIVE index generation safe and atomic"
```

### Task 2: Build the Bounded Orientation Projection

**Files:**
- Create: `plugins/alive/scripts/orientation.py`
- Create: `codex/tests/test_orientation_projection.py`
- Modify: `codex/shared-runtime.json`
- Synchronize: `codex/scripts/orientation.py`

**Interfaces:**
- Consumes: `build_orientation(world_root: Path, index_payload: dict, today: date)`.
- Produces: `.alive/_orientation.json`, `render_orientation(payload, limit=3) -> str`.

- [ ] **Step 1: Write failing tests for deterministic task exceptions**

```python
def test_detects_expired_dates_overdue_and_status_contradictions(self):
    self.write_tasks([
        {"id": "t001", "title": "Call them tomorrow", "status": "todo",
         "priority": "urgent", "created": "2026-05-14"},
        {"id": "t002", "title": "Submit invoice", "status": "active",
         "priority": "active", "created": "2026-07-01", "due": "2026-07-20"},
        {"id": "t003", "title": "Waiting: Dave to reply", "status": "todo",
         "priority": "urgent", "created": "2026-07-24"},
        {"id": "t004", "title": "Strategy phase COMPLETE", "status": "active",
         "priority": "active", "created": "2026-07-24"},
    ])
    payload = self.build(today=date(2026, 7, 25))
    kinds = [item["kind"] for item in payload["recommendations"]]
    self.assertIn("expired_relative_date", kinds)
    self.assertIn("overdue", kinds)
    self.assertIn("blocked_status_mismatch", kinds)
    self.assertIn("completed_status_mismatch", kinds)
```

- [ ] **Step 2: Write the false-positive and bounds tests**

```python
def test_age_alone_does_not_call_a_task_dead(self):
    self.write_tasks([{
        "id": "t001", "title": "Long-running research", "status": "active",
        "priority": "active", "created": "2026-01-01",
        "assignee": "Ben", "due": None,
    }])
    payload = self.build(today=date(2026, 7, 25))
    self.assertFalse(any("dead" in item["kind"] for item in payload["recommendations"]))
    self.assertFalse(any(item.get("proposed_action") == "drop_task"
                         for item in payload["recommendations"]))

def test_projection_is_bounded_and_deterministic(self):
    self.write_many_defective_tasks(40)
    first = self.build(today=date(2026, 7, 25))
    second = self.build(today=date(2026, 7, 25))
    self.assertEqual(first["recommendations"], second["recommendations"])
    self.assertLessEqual(len(first["recommendations"]), 9)
    encoded = json.dumps(first, separators=(",", ":")).encode()
    self.assertLessEqual(len(encoded), 8192)
    self.assertLessEqual(len(render_orientation(first).encode()), 8192)
```

- [ ] **Step 3: Run the projection tests and verify they fail**

Run:

```bash
python3 -m unittest codex.tests.test_orientation_projection -v
```

Expected: import failure because `orientation.py` does not exist.

- [ ] **Step 4: Implement normalized task iteration**

Implement:

```python
OPEN_STATUSES = {"todo", "active", "waiting", "scheduled", "blocked"}

def iter_task_records(world_root, index_payload):
    for walnut in index_payload.get("walnuts", []):
        walnut_root = world_root / walnut["path"]
        for tasks_file in discover_task_files(walnut_root):
            payload = json.loads(tasks_file.read_text(encoding="utf-8"))
            for task in payload.get("tasks", []):
                yield {
                    "walnut": walnut["name"],
                    "path": tasks_file.relative_to(world_root).as_posix(),
                    "task": task,
                }
```

Discovery must skip `.git`, `node_modules`, `raw`, archives and nested walnut
boundaries, matching `tasks.py` behaviour.

- [ ] **Step 5: Implement pure recommendation rules**

Create one pure detector per rule:

```python
def expired_relative_date(record, today): ...
def overdue(record, today): ...
def blocked_status_mismatch(record, today): ...
def completed_status_mismatch(record, today): ...
def urgent_unowned(record, today): ...
```

Each returns `None` or a complete recommendation object. Relative-date rules
must anchor interpretation to `created`; if `created` is absent or malformed,
return `None`.

- [ ] **Step 6: Implement deterministic ranking and whole-object truncation**

```python
SEVERITY_ORDER = {"critical": 0, "warning": 1, "notice": 2}
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}

def rank_key(item):
    return (
        SEVERITY_ORDER[item["severity"]],
        CONFIDENCE_ORDER[item["confidence"]],
        item.get("sort_date", "9999-12-31"),
        item["id"],
    )
```

Sort, cap at nine, serialize compactly, and remove lowest-ranked whole objects
until the payload is at most 8,192 bytes. Record `total_detected` separately.

- [ ] **Step 7: Implement atomic CLI generation and rendering**

CLI:

```text
python3 scripts/orientation.py build WORLD_ROOT [--today YYYY-MM-DD]
python3 scripts/orientation.py render WORLD_ROOT [--limit 3]
```

`build` reads `.alive/_index.json` and writes `_orientation.json` atomically.
`render` validates schema version and size, then prints one summary line plus
at most three numbered recommendations.

- [ ] **Step 8: Run projection tests and verify they pass**

Run:

```bash
python3 -m unittest codex.tests.test_orientation_projection -v
```

Expected: all orientation projection tests pass.

- [ ] **Step 9: Add `scripts/orientation.py` to the shared runtime allowlist and sync**

Modify `codex/shared-runtime.json`:

```json
"files": [
  "scripts/generate-graph.py",
  "scripts/generate-index.py",
  "scripts/orientation.py",
  "scripts/project.py",
  "scripts/tasks.py"
]
```

Run the sync and check commands from Task 1.

- [ ] **Step 10: Commit the bounded projection**

```bash
git add plugins/alive/scripts/orientation.py \
  codex/scripts/orientation.py \
  codex/shared-runtime.json \
  codex/tests/test_orientation_projection.py
git commit -m "feat: add bounded ALIVE orientation projection"
```

### Task 3: Refresh Orientation From the Explicit Codex Generation Path

**Files:**
- Modify: `plugins/alive/scripts/generate-index.py`
- Synchronize: `codex/scripts/generate-index.py`
- Modify: `codex/tests/test_index_generation.py`

**Interfaces:**
- Consumes: `orientation.build_and_write(world_root, json_data)` only when the
  caller passes `--build-orientation`.
- Produces: the current `_index.json` and `_index.yaml` pair by default, plus
  `_orientation.json` for the explicit Codex projection run.

- [ ] **Step 1: Write the failing integration test**

```python
def test_codex_flag_refreshes_orientation(self):
    result = self.run_generator(build_orientation=True)
    self.assertEqual(0, result.returncode, result.stderr)
    orientation = json.loads(
        (self.world / ".alive" / "_orientation.json").read_text()
    )
    self.assertEqual(1, orientation["schema_version"])
    self.assertTrue(orientation["health"]["index_valid"])
```

- [ ] **Step 2: Run the test and verify it fails**

Run:

```bash
python3 -m unittest \
  codex.tests.test_index_generation.IndexGenerationTests.test_shared_generator_does_not_refresh_orientation_without_codex_flag \
  -v
```

Expected: `_orientation.json` is missing until the explicit flag is used.

- [ ] **Step 3: Call the orientation builder after successful index replacement**

Lazy-load the sibling module only on the explicit Codex path:

```python
if args.build_orientation:
    from orientation import build_and_write
```

After both index files have been atomically replaced:

```python
if args.build_orientation:
    build_and_write(Path(world_root), json_data, index_path=Path(json_file))
```

If orientation generation fails, keep the valid indexes and leave the previous
orientation intact. The caller reports the failed refresh truthfully.

- [ ] **Step 4: Run integration and shared-runtime tests**

Run:

```bash
python3 -m unittest \
  codex.tests.test_index_generation \
  codex.tests.test_orientation_projection \
  codex.tests.test_shared_runtime \
  -v
```

Expected: all tests pass.

- [ ] **Step 5: Synchronize and commit**

```bash
python3 codex/scripts/sync_shared_runtime.py \
  --source-root plugins/alive \
  --plugin-root codex \
  --manifest codex/shared-runtime.json
git add plugins/alive/scripts/generate-index.py \
  codex/scripts/generate-index.py \
  codex/tests/test_index_generation.py
git commit -m "feat: refresh ALIVE orientation after projection"
```

### Task 4: Make Codex Hooks Consume Only Bounded Orientation

**Files:**
- Modify: `codex/hooks/scripts/alive-session-start.sh`
- Modify: `codex/hooks/scripts/alive-session-resume.sh`
- Modify: `codex/tests/test_hook_runtime.py`

**Interfaces:**
- Consumes: `scripts/orientation.py render WORLD_ROOT --limit 3`.
- Produces: Codex `additionalContext` containing short recovery state and bounded recommendations.

- [ ] **Step 1: Write failing startup and resume hook tests**

```python
def test_session_start_injects_bounded_orientation_not_full_index(self):
    self.write_orientation(summary="9 things need attention")
    world.joinpath(".alive", "_index.yaml").write_text("SECRET_FULL_INDEX")
    result = self.run_start(world)
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    self.assertIn("9 things need attention", context)
    self.assertNotIn("SECRET_FULL_INDEX", context)
    self.assertLessEqual(len(context.encode()), 8192)

def test_missing_orientation_is_nonfatal(self):
    result = self.run_start(world)
    self.assertEqual(0, result.returncode)
    self.assertIn("No walnut has been loaded", result.stdout)
```

- [ ] **Step 2: Run focused hook tests and verify failure**

Run:

```bash
python3 -m unittest codex.tests.test_hook_runtime -v
```

Expected: startup output lacks the orientation summary.

- [ ] **Step 3: Add a shared shell helper for cached rendering**

In `alive-common-codex.sh`, add:

```bash
read_bounded_orientation() {
  local renderer="$PLUGIN_ROOT/scripts/orientation.py"
  [ -f "$renderer" ] || return 0
  python3 "$renderer" render "$WORLD_ROOT" --limit 3 2>/dev/null || true
}
```

Use its output in start and resume messages only when non-empty. Do not invoke
the `build` command from either hook.

- [ ] **Step 4: Run hook contract and runtime tests**

Run:

```bash
python3 -m unittest \
  codex.tests.test_hook_contract \
  codex.tests.test_hook_runtime \
  -v
```

Expected: all hook tests pass and contexts remain bounded.

- [ ] **Step 5: Commit Codex hook consumption**

```bash
git add codex/hooks/scripts/alive-common-codex.sh \
  codex/hooks/scripts/alive-session-start.sh \
  codex/hooks/scripts/alive-session-resume.sh \
  codex/tests/test_hook_runtime.py
git commit -m "feat: surface bounded ALIVE orientation in Codex"
```

### Task 5: Claude Hook Migration — Deferred Pending Evaluation

This task is deliberately not implemented in alpha.3. Claude still uses the
legacy full-index and broader-context hook behavior. Its hook tree and
`plugins/alive/tests/test_orientation_hooks.py` must remain byte-identical to
baseline `c9d6d7e`.

Before this task can be reopened, run the separate Claude lifecycle evaluation
against the current baseline and proposed bounded-orientation variant. Only
evidence that the change preserves or improves recovery, retrieval and hook
reliability authorizes a Claude runtime change. Until then, documentation must
state the limitation and must not claim Codex/Claude lifecycle parity.

### Task 6: Align Skills, Doctor and Private-Alpha Documentation

**Files:**
- Modify: `codex/skills/alive-world/SKILL.md`
- Modify: `codex/skills/alive-search-world/SKILL.md`
- Modify: `codex/doctor.sh`
- Modify: `codex/docs/v3.3/context-pruning.md`
- Modify: `codex/docs/private-alpha/compatibility.md`
- Modify: `codex/docs/private-alpha/public-release-gaps.md`
- Modify: `codex/tests/test_package_contract.py`

**Interfaces:**
- Consumes: `_index.json` for on-demand retrieval and `_orientation.json` for startup.
- Produces: truthful runtime instructions and doctor results.

- [ ] **Step 1: Add failing documentation and doctor contract assertions**

```python
def test_world_skill_does_not_claim_full_index_is_injected(self):
    text = (PLUGIN_ROOT / "skills/alive-world/SKILL.md").read_text()
    self.assertNotIn("Read the injected `<WORLD_INDEX>`", text)
    self.assertIn("_orientation.json", text)
    self.assertIn("_index.json", text)

def test_package_contains_orientation_runtime(self):
    self.assertTrue((PLUGIN_ROOT / "scripts/orientation.py").is_file())
```

Extend doctor tests to expect checks for valid `_index.json`, bounded
`_orientation.json`, supported schema version and maximum byte size.

- [ ] **Step 2: Run contract tests and verify failure**

Run:

```bash
python3 -m unittest codex.tests.test_package_contract -v
```

Expected: old injected-index claim remains.

- [ ] **Step 3: Rewrite retrieval instructions**

Document:

- `_orientation.json` is cached and automatically surfaced;
- `_index.json` is read or queried only for world/search requests;
- hooks do not guarantee background refresh;
- explicit save/project is the guaranteed refresh path;
- stale/missing orientation is reported, not regenerated during startup.

- [ ] **Step 4: Add doctor checks**

Doctor must fail clearly for:

- malformed `_index.json`;
- `_orientation.json` above 8,192 bytes;
- unsupported orientation schema;
- orientation generated before the current index;
- a package skill that still claims the full index is injected.

- [ ] **Step 5: Run package, doctor and compatibility tests**

Run:

```bash
python3 -m unittest \
  codex.tests.test_package_contract \
  codex.tests.test_install_lifecycle \
  codex.tests.test_hook_contract \
  -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit truthful documentation**

```bash
git add codex/skills/alive-world/SKILL.md \
  codex/skills/alive-search-world/SKILL.md \
  codex/doctor.sh \
  codex/docs/v3.3/context-pruning.md \
  codex/docs/private-alpha/compatibility.md \
  codex/docs/private-alpha/public-release-gaps.md \
  codex/tests/test_package_contract.py
git commit -m "docs: define ALIVE index and orientation boundaries"
```

### Task 7: Run Full Verification and Real-World Read-Only Proof

**Files:**
- Modify: `codex/docs/private-alpha/3.3.0-alpha.3.md`
- Create: `codex/tests/fixtures/orientation-world/README.md`

**Interfaces:**
- Consumes: completed index and orientation implementation.
- Produces: regression evidence suitable for the private-alpha release notes.

- [ ] **Step 1: Run the complete Codex unit suite**

Run:

```bash
(cd codex && python3 -m unittest discover -s tests -v)
```

Expected: all tests pass.

- [ ] **Step 2: Run the MCP suite**

Run:

```bash
cd codex/mcp
python3 -m pytest -q
```

Expected: all MCP tests pass.

- [ ] **Step 3: Run shared-runtime drift verification**

Run:

```bash
python3 codex/scripts/sync_shared_runtime.py \
  --source-root plugins/alive \
  --plugin-root codex \
  --manifest codex/shared-runtime.json \
  --check
```

Expected: `{"divergent": []}`.

- [ ] **Step 4: Generate against `/Users/benflint/MyWorld` read-only except generated projections**

First copy the current three projections to a temporary evidence directory.
Run the packaged index generator against the real world, then verify:

```bash
python3 -c 'import json; from pathlib import Path; p=Path("/Users/benflint/MyWorld/.alive/_index.json"); d=json.loads(p.read_text()); print(d["recent_sessions"][0:10])'
python3 codex/scripts/orientation.py render /Users/benflint/MyWorld --limit 3
wc -c /Users/benflint/MyWorld/.alive/_orientation.json
```

Expected:

- the `019f82cf` tags have no leading dash;
- orientation is no larger than 8,192 bytes;
- known temporal/status defects are detected;
- the underlying walnut task and kernel files are unchanged.

- [ ] **Step 5: Run install, upgrade and uninstall lifecycle tests**

Run:

```bash
python3 -m unittest \
  codex.tests.test_install_lifecycle \
  codex.tests.test_marketplace_build \
  codex.tests.test_walnut_recovery \
  -v
```

Expected: all tests pass.

- [ ] **Step 6: Document verified claims and limitations**

Release notes must state:

- the full index is no longer injected at startup;
- deterministic recommendations are local and cached;
- hooks are best-effort and do not guarantee background refresh;
- explicit save/project remains the guaranteed refresh path;
- no task is automatically completed, dropped or rewritten.

- [ ] **Step 7: Commit verification evidence**

```bash
git add codex/docs/private-alpha/3.3.0-alpha.3.md \
  codex/tests/fixtures/orientation-world/README.md
git commit -m "test: verify bounded ALIVE orientation end to end"
```

## Self-Review

- Spec coverage: index corruption, atomic preservation, bounded orientation,
  deterministic recommendations, cross-runtime hook behaviour, privacy,
  truthful lifecycle limits and real-world evidence each map to a task.
- Scope boundary: typed task mutation is intentionally deferred to its own
  plan; this plan only classifies legacy task records read-only.
- Placeholder scan: no `TBD`, `TODO`, “implement later”, or unspecified test
  steps remain.
- Interface consistency: all tasks use `orientation.py build`, `render`,
  `build_and_write`, schema version `1`, size `8,192`, stored limit `9`, and
  rendered limit `3`.
