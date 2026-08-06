# Changelog

All notable changes to the ALIVE Context System plugin are documented here.

## [3.2.1] - 2026-08-07

### Fixed

- **Migration boundary:** Live-disk fallback now requires walnut identity before treating a `bundles/` directory as migratable. Generic project folders are not moved.
- **Resume recovery:** A resumed Claude Code session with a missing squirrel record gets a new exact session record instead of borrowing another active session.
- **Upgrade warning:** A v3 `02_Life/_kernel` path or unrelated nested `bundles/` directory no longer triggers the v2 migration warning by itself.
- **Completed task history:** Completed and dropped tasks are listable from history (issue #60).
- **Release metadata:** README, marketplace, plugin, runtime and walnut product versions agree at 3.2.1. The world schema target remains 3.2.0.

### Changed

- Licence remains MIT.
- Added a buyer-facing permission declaration covering 14 command invocations across 5 Claude Code hook event types (`PERMISSIONS.md`).
- The README now shows the complete first-time marketplace registration and plugin installation flow.
- Claude Code remains the only supported runtime in this release. Codex support is not included; Hermes remains community/experimental.

## [3.0.0] - 2026-04-04

### Personal Context Manager

The GTM release. Two weeks live, 500+ installs, and a full architectural refactor based on real usage feedback. Every pain point from v2 — slow loads, broken task tracking, concurrent session clobbering, too many file reads — addressed in this release. Install: `claude plugin install alive@alivecontext`

### Architecture
- **Flat kernel:** `_kernel/_generated/` removed. All files flat in `_kernel/` — key.md, log.md, insights.md, tasks.json, now.json, completed.json
- **Flat bundles:** `bundles/` container removed. Bundles live flat in walnut root, identified by `context.manifest.yaml`
- **Script-operated tasks:** `tasks.md` replaced by `tasks.json`. Agent calls `tasks.py` CLI — never reads/writes task files directly
- **True projection:** `now.json` computed post-save by `project.py` from ALL source files. Agent never writes now.json. Solves concurrent session clobbering.
- **3-file load:** key.md + now.json + insights.md frontmatter. Down from 13+ file reads.
- **03_Inputs/ → 03_Inbox/** — I = Inbox. Universally understood.
- **Graduation is a status flip** — no folder moves. Bundle stays where it is.
- **observations.md removed** — stash routes to log at save. No separate file.

### Added
- **`tasks.py`** — CLI for all task operations (add, done, drop, edit, list, summary)
- **`project.py`** — projection script, builds now.json from all sources post-save
- **`completed.json`** — append-only archive of every completed/dropped task
- **Subagent brief template** — ships with plugin, substituted at dispatch time
- **DO NOT READ guards** — load-context and world skills explicitly bar unnecessary file reads
- **Walnut boundary detection** — scripts stop at nested walnut boundaries, no more scanning 693 directories

### Changed
- **Org:** stackwalnuts → alivecontext. GitHub, install command, all URLs.
- **Author:** Stack Walnuts → Lock-in Lab
- **Category:** plugin → pcm (Personal Context Manager)
- **Twitter:** @ALIVE_context
- **All 6 rules rewritten** for v3 (version 3.0.0)
- **All 15 skills updated** — 6 major rewrites, 9 moderate/minor
- **5 hooks updated** — project.py trigger, v3 paths, backward compat
- **generate-index.py** — reads v3 flat now.json, extracts task counts, includes recent sessions and unsigned stash count
- **Save protocol:** agent writes source files, projection script computes now.json
- **Stash checkpoint rule removed** — save IS the checkpoint, no phantom timers
- **Unsigned entry recovery fixed** — stash: [] does NOT mean empty session, check transcripts
- **Archive enforcer hook removed** — Claude Code permissions sufficient

### Removed
- `plugins/walnut/` — dead v1 plugin (43 files)
- `plugins/walnut-cowork/` — empty stub
- `assets/` — 13 orphaned images
- `observations.md` from bundle anatomy
- `_kernel/_generated/` subdirectory
- `bundles/` container directory

### Upgrade
```bash
claude plugin install alive@alivecontext
/alive:system-upgrade
```
Handles v1→v3 and v2→v3. Backs up everything before migrating. Tasks.md parsed to tasks.json. Bundles flattened. Kernel flattened. Inbox renamed.

---

## [2.0.0] - 2026-03-29

### The ALIVE Context System

Complete architecture overhaul. Product name: ALIVE Context System. Plugin: `alive`. Install: `claude plugin install alive@alivecontext`.

### Architecture
- **Kernel replaces core:** `_core/` -> `_kernel/`. Three source files: key.md, log.md, insights.md
- **Bundles replace capsules:** `_capsules/` -> `bundles/` (promoted to walnut top level). Two species: outcome and evergreen.
- **Generated projections:** now.md deleted, replaced by generated `now.json`. Tasks distributed to bundles.
- **Context manifest:** `companion.md` -> `context.manifest.yaml` -- integration manifest + marketplace listing
- **Projection tiers:** world-index.json -> now.json -> manifests -> raw. Generated on save.
- **People/ reverted** to `02_Life/people/` -- people walnuts stay inside the Life domain, not at world root
- **Subagent brief pack:** `.alive/_generated/subagent-brief.md` injected into all spawned agents

### Added
- **`alive:bundle` skill** -- create, share, graduate bundles (replaces capsule-manager)
- **`alive:system-upgrade` skill** -- upgrade from any previous version with visual plan
- **Named squirrels** -- users name their context companion (persona layer)
- **Action logging** -- proof of work in squirrel YAML
- **Plugin compatibility watch** -- detect conflicts with other plugins, suggest ALIVE-compatible patterns
- **Cross-platform support** -- python3 primary, node fallback, Unicode platform-guarded

### Changed
- **Namespace:** `walnut:*` -> `alive:*` (15 skills)
- **System folder:** `.walnut/` -> `.alive/`
- **6 rules rewritten** for v2 architecture (bundles.md replaces capsules.md)
- **14 hooks updated** for v2 paths and cross-platform safety
- **README rewritten** -- ALIVE story, two units, projections, install guide

### Walnut v1 (sunset)
- `plugins/walnut/` preserved as frozen v1. Install: `claude plugin install walnut@walnut`
- No further updates. Use `alive:system-upgrade` to migrate.

## [1.0.1-beta] -- 2026-03-12

### Added
- Capsule architecture -- self-contained units of work
- 3 new skills: mine-for-context, build-extensions, my-context-graph
- Inbox scan mode, context graph, world index generator

## [1.0.0-beta] -- 2026-03-10

### Added
- 12 skills, 6 rules, 12 hooks
- Squirrel caretaker runtime, stash mechanic, ALIVE framework
- Onboarding, statusline, templates

## [0.1.0-beta] -- 2026-02-23

Initial release.
