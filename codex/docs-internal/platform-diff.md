# ALIVE — Claude Code vs Codex CLI Platform Diff

**Status:** Research document, v1. Written 2026-04-17.
**Scope:** Everything that will break, bend, or need adaptation when porting the ALIVE plugin from Claude Code to OpenAI Codex CLI.
**Audience:** Ben, Patrick, future contributors.

---

## Executive verdict

**This is a port with rewrite-shaped holes, not a clone.**

The surface looks almost identical — both platforms have a `.codex-plugin/` / `.claude-plugin/` manifest, both bundle `skills/`, both support MCP over stdio, both have AGENTS.md/CLAUDE.md rule files, and Codex even copied Claude's hook event names (`SessionStart`, `PreToolUse`, `PostToolUse`, `UserPromptSubmit`, `Stop`). Roughly 70% of ALIVE's structure maps one-to-one.

The remaining 30% is where it hurts:

1. **No `PreCompact` hook in Codex.** Auto-compaction is the single most important lifecycle event for a context-management system, and Codex has no deterministic point to intercept it. Request exists as GitHub issue [#12208](https://github.com/openai/codex/issues/12208), closed as duplicate of [#2109](https://github.com/openai/codex/issues/2109), still unshipped as of April 2026.
2. **Hooks are behind a feature flag (`codex_hooks = true`) and marked "under development".** Every user of ALIVE-on-Codex has to opt in, and the schema may drift.
3. **Matchers are weaker.** Codex `PreToolUse` only matches `Bash` and `apply_patch` — there is no equivalent of Claude's `Edit|Write` regex because those tools don't exist as distinct tool names in Codex. All file mutation funnels through `apply_patch`. Our four guardians (log, rules, root, archive) all have to be rewritten to parse unified diffs instead of tool args.
4. **Model behaviour is genuinely different.** GPT-5-Codex is stronger on multi-step benchmarks but weaker on "maintain a running stash across 40 turns while following a 28KB rule file" — Claude Opus is more consistent on long, constraint-heavy system prompts ([source](https://www.mindstudio.ai/blog/gpt-5-4-vs-claude-opus-4-6-comparison), [source](https://blog.getbind.co/claude-sonnet-4-5-vs-gpt-5-vs-claude-opus-4-1-ultimate-coding-comparison/)). ALIVE's save protocol, boot-sequence persona, and rule-file loyalty will degrade without retuning.
5. **Codex auto-compaction is known-buggy.** Issue [#5957](https://github.com/openai/codex/issues/5957) documents GPT-5-Codex denying it made edits it just made, after compaction fires mid-task. That is catastrophic for a context-manager.

**Bottom line:** the shell of the port is already done (`/Users/benflint/aliveplugindev/codex/` has plugin.json, hooks.json, skills/ stubs, MCP wired up). What remains is adapting the hook scripts to `apply_patch`, rewriting the save/compaction story without `PreCompact`, reworking persona/squirrel prose for GPT-5's tighter instruction-following style, and accepting that some ALIVE features (background dispatch, pre-compact stashing) will either be disabled or moved into user-driven slash-commands on the Codex side.

---

## 1. Agent model behaviour

### 1.1 Multi-step skill protocols (e.g. ALIVE save protocol)

**Claude Code (Sonnet 4.5 / Opus 4.6):** Best-in-class at following long multi-step protocols written in prose. Our save protocol is ~40 steps across 5 phases; Claude follows it without reminders. Opus especially holds steady across long contexts with many simultaneous constraints ([source](https://www.mindstudio.ai/blog/gpt-5-4-vs-claude-opus-4-6-comparison)).

**Codex (GPT-5-Codex):** Higher raw score on τ²-Bench multi-step (84–87% vs Sonnet's 78%, Opus's 71%) but "thinking mode" is what gets it there ([source](https://portkey.ai/blog/claude-sonnet-4-5-vs-gpt-5/)). Observed behaviour: GPT-5-Codex is more surgical and more likely to short-circuit a protocol it deems redundant. ALIVE's save protocol has deliberate "slow" steps (stash before write, verify after write) that GPT-5 may skip unless we phrase them as hard preconditions.

**Impact on ALIVE:** Save, load-context, session-context-rebuild, mine-for-context all need to be restructured from "here is a 12-step narrative" into "here are 12 preconditions; each one either holds or blocks the next step." The Claude prose style of "Now, carefully, take the following action..." reads as filler to GPT-5.

### 1.2 Maintaining a running stash in conversation

**Claude Code:** Strong. The stash pattern (model holds decisions in a structured block, appends through the turn, writes out at save time) works because Sonnet/Opus maintain self-referential state well across long turns.

**Codex:** Weaker, and worse: auto-compaction can wipe mid-task state without warning ([#5957](https://github.com/openai/codex/issues/5957)). GPT-5-Codex has denied making edits it made moments before compaction. A running stash kept purely in-conversation is unsafe on Codex.

**Impact on ALIVE:** The stash must be **persisted to disk on every append** on Codex, not held in conversation. This is already half-true (stash file in `_squirrels/`) but the Claude version trusts model memory between append and write; the Codex version can't. Likely fix: `alive-save` skill flushes stash to disk on every decision-tick.

### 1.3 Rule file behaviour — AGENTS.md vs CLAUDE.md

| | Claude Code | Codex |
|---|---|---|
| File name | `CLAUDE.md` (project), `~/.claude/CLAUDE.md` (global) | `AGENTS.md` (project, walks up from cwd to git root), `~/.codex/AGENTS.md` (global) |
| Override | none | `AGENTS.override.md` at same scope |
| Size limit | Not hard-published; large files degrade quality | **32 KiB hard cap** via `project_doc_max_bytes` ([source](https://developers.openai.com/codex/guides/agents-md)) |
| Truncation | Soft (model just uses what fits) | Hard (Codex stops concatenating once cap reached) |
| Rebuild | Per session | **Per run** — no persistent cache |
| Loyalty | Very high (Opus especially) | Moderate — GPT-5 follows rules but is more willing to "interpret" |

**Impact on ALIVE:** ALIVE's README claims "81KB of behavioural spec condensed into 28KB AGENTS.md." 28KB is under the 32 KiB cap but dangerously close. If we ever need to add content, we hit the wall. Two options:
- Split across nested `.alive/AGENTS.md` files (Codex walks up, so nested files get concatenated).
- Use the `AGENTS.override.md` mechanism for user-scoped rules so the plugin's AGENTS.md stays lean.

Also: Codex rebuilds the instruction chain **every run**, not per session. Any caching we assume from CLAUDE.md side is gone.

### 1.4 Persona injection ("you are a squirrel")

**Claude Code:** Strong persona adoption. Claude will genuinely inhabit "squirrel" persona for entire sessions.

**Codex:** GPT-5 is measurably more resistant to persona/role-prompting than prior GPTs. Research shows "for smarter models, the effect of using a simple persona is not really going to do much" ([source](https://www.prompthub.us/blog/role-prompting-does-adding-personas-to-your-prompts-really-make-a-difference)). GPT-5 also has its own baked-in personalities (Cynic, Robot, Listener, Nerd) which can clash with injected ones ([source](https://www.arsturn.com/blog/how-to-work-around-gpt-5-personalities)).

**Impact on ALIVE:** The squirrel metaphor is load-bearing in ALIVE's UX. On Codex it will feel more like a label than an embodied voice. Two mitigations:
- Don't lean on persona — lean on structure. Squirrels as data type, not as voice.
- If voice is needed, set `personality` in Codex `config.toml` and hope users haven't overridden.

### 1.5 Visual conventions (Unicode bordered blocks)

**Claude Code:** Renders Unicode box-drawing consistently. ALIVE uses these heavily for save summaries, boot banners, the Squirrel Council block.

**Codex:** Renders the same Unicode but the model is less consistent about producing them. GPT-5-Codex has been trained to prefer tight, minimal output. It will generate boxed blocks when instructed but often trims borders or substitutes ASCII. Also: Codex `apply_patch` is stricter about whitespace than Claude's Edit tool, so bordered blocks written *into files* (not just rendered in chat) round-trip more reliably on Codex.

**Impact on ALIVE:** Acceptable; our bordered blocks are mostly in-chat UX, not on-disk state. Keep them; expect ~10% rendering drift.

### 1.6 Sycophancy and agreement

**Claude Code:** Moderate sycophancy risk. Sonnet/Opus will agree with a bad user assertion if phrased confidently. ALIVE's "stop cooking" and "never-replace-testimonials" feedback entries exist because Claude does this.

**Codex:** GPT-5 actively trained against sycophancy — targeted evals show drop from 14.5% to <6% ([source](https://openai.com/index/introducing-gpt-5/)). So Codex is **less sycophantic by default**, which is good, but GPT-5 is also more likely to push back on user decisions in ways that read as contrarian. "Mob rule and sycophancy" OpenAI forum thread documents users finding GPT-5 too blunt ([source](https://community.openai.com/t/mob-rule-and-sycophancy-gpt-5-and-chatgpt/1347904)).

**Impact on ALIVE:** Probably neutral-to-positive. The ALIVE rules file can lose some of its anti-sycophancy framing on Codex. But the Squirrel Council persona (supportive tone) may feel mismatched with GPT-5's blunter baseline.

---

## 2. Hook system differences

### 2.1 Event coverage

| Event | Claude Code | Codex | Notes |
|---|---|---|---|
| `SessionStart` | Yes (matchers: `startup`, `resume`, `compact`) | Yes (matchers: `startup`, `resume`) | **No `compact` matcher** in Codex |
| `SessionEnd` | Yes | No documented equivalent | Gap |
| `PreToolUse` | Yes (regex matchers on any tool name) | Yes (matchers: `Bash`, `apply_patch` only) | Severely limited |
| `PostToolUse` | Yes (regex matchers on any tool name) | Yes (same limitation) | Severely limited |
| `UserPromptSubmit` | Yes | Yes (no matcher) | OK |
| `Stop` | Yes | Yes (no matcher) | OK |
| `SubagentStart` / `SubagentStop` | Yes | No documented equivalent | Gap |
| `PreCompact` | **Yes** | **No** ([#12208](https://github.com/openai/codex/issues/12208)) | **Critical gap** |
| `Notification` | Yes | Partial (`agent-turn-complete` via `notify` config) | Different shape |

Source: [Codex hooks docs](https://developers.openai.com/codex/hooks), [Claude Code hooks](https://code.claude.com/docs/en/hooks).

### 2.2 Feature flag

Codex hooks are **off by default**. User must set `features.codex_hooks = true` in `config.toml`. The feature is documented as "under development" — schema may change ([source](https://developers.openai.com/codex/config-advanced)). ALIVE's install doc will need a mandatory step: "enable codex_hooks."

### 2.3 What ALIVE hooks break

Walking `/Users/benflint/aliveplugindev/plugins/alive/hooks/hooks.json` against Codex capabilities:

| ALIVE hook | Claude event | Codex status |
|---|---|---|
| `alive-session-new.sh` | SessionStart/startup | Portable |
| `alive-repo-detect.sh` (x2) | SessionStart/startup + compact | Partial — no `compact` matcher, so repo-redetect on compaction is lost |
| `alive-session-resume.sh` | SessionStart/resume | Portable |
| `alive-session-compact.sh` | SessionStart/compact | **Broken — no compact matcher** |
| `alive-log-guardian.sh` | PreToolUse/Edit\|Write | Rewrite — matcher becomes `apply_patch`, script must parse diff |
| `alive-rules-guardian.sh` | PreToolUse/Edit\|Write | Rewrite — same |
| `alive-root-guardian.sh` | PreToolUse/Edit\|Write | Rewrite — same |
| `alive-external-guard.sh` | PreToolUse/mcp__.* | **Broken — no MCP tool matcher in Codex** |
| `alive-post-write.sh` | PostToolUse/Write\|Edit | Rewrite — matcher becomes `apply_patch`, script parses diff |
| `alive-inbox-check.sh` | PostToolUse/Write\|Edit | Rewrite — same |
| `alive-context-watch.sh` | UserPromptSubmit | Portable |
| `alive-background-dispatch.sh` | UserPromptSubmit | Portable but see §6 re: always-on crons |
| `alive-pre-compact.sh` | **PreCompact** | **Broken — event does not exist** |

**Score:** 5 portable, 6 need rewrites, 2 broken beyond rewrite.

### 2.4 The PreCompact replacement problem

ALIVE's `alive-pre-compact.sh` serialises the stash, dumps decisions to `_squirrels/`, and writes a breadcrumb so the post-compaction session can reload. This is the single most-important hook ALIVE ships.

Codex has **no deterministic replacement**. Options, worst to best:

1. **Disable and warn.** Document that on Codex, compaction is lossy. User must manually `/save` before hitting ~85% context. Unacceptable for PCM's core promise.
2. **Poll via UserPromptSubmit.** On every user prompt, check `token_count` (if exposed — it's not cleanly in the Codex hook input today) and if above threshold, force a save. Brittle.
3. **Stash on every PostToolUse.** Expensive but deterministic. Every file mutation triggers a stash flush. Combined with persisting stash to disk (§1.2) this is likely the real answer.
4. **Patch Codex upstream.** Contribute `PreCompact` to Codex. OpenAI has been receptive to lifecycle hook requests but slow.

**Recommendation:** Option 3 (stash-on-every-PostToolUse) as the default, with a loud documented warning that Codex ALIVE has weaker compaction semantics until OpenAI ships `PreCompact`.

---

## 3. Tool system differences

| Claude Code | Codex | Comment |
|---|---|---|
| `Read` | `shell` (`cat`/`head`) | Codex reads via shell. No dedicated read tool. Our skills that say "use Read" need to say "read the file" neutrally. |
| `Write` | `apply_patch` | Codex has no whole-file-create tool; new files are created via `apply_patch` with `*** Add File:` envelope. |
| `Edit` | `apply_patch` | Codex forces unified-diff syntax for all edits. |
| `MultiEdit` | `apply_patch` (multiple hunks) | Codex handles multi-file via multiple patch hunks in one call. |
| `Glob` | `shell` (`find`/`fd`) | No dedicated tool. Skills that say "use Glob" → "list files matching pattern." |
| `Grep` | `shell` (`rg`) | Same. |
| `Bash` | `shell` | Equivalent. |
| `Task` / subagents | `subagents` ([docs](https://developers.openai.com/codex/subagents)) | Codex only spawns subagents when user **explicitly asks**. No auto-delegation like Claude's Task tool. |
| `WebFetch` / `WebSearch` | `web_search` config toggle | Codex has web search via `[tools] web_search = true`. No direct equivalent of WebFetch's "fetch + prompt over content" flow. |
| `NotebookEdit` | None | Not a loss for ALIVE. |

### 3.1 Tools ALIVE skills assume

Running the ALIVE skills against the tool list:

- **alive-save** — assumes Edit/Write. Becomes `apply_patch`. Mechanical rewrite.
- **alive-load-context** — assumes Read/Glob/Grep. Becomes shell. Mechanical.
- **alive-mine-for-context** — assumes WebFetch for URL expansion. **Broken on Codex** unless we build an MCP tool.
- **alive-search-world** — assumes Grep with regex. Becomes `rg`. Mechanical.
- **alive-capture-context** — pure file I/O. Mechanical.
- **alive-bundle** — pure file I/O. Mechanical.
- **alive-session-context-rebuild** — assumes Read+Grep. Mechanical.
- **alive-world** — assumes Read/Glob. Mechanical.
- **alive-my-context-graph** — calls MCP. Portable.
- **alive-boot-sequence** — pure instructions + shell. Mechanical.
- **alive-create-walnut** — file I/O. Mechanical.
- **alive-build-extensions** — file I/O + shell. Mechanical.

**Score:** 11 mechanical rewrites, 1 broken (`alive-mine-for-context` needs WebFetch replacement).

### 3.2 The `apply_patch` constraint

Codex's `apply_patch` is stricter than Claude's Edit tool: exact whitespace, unified-diff envelope, atomic. Skills that tell the agent to "edit this line" need to be rewritten as "produce a unified diff that edits this line." For ALIVE save protocol, which writes structured blocks into `decisions.md`, this is fine — the protocol already operates on whole-section replacement. But the four guardians (`log-guardian`, `rules-guardian`, `root-guardian`, `archive-enforcer`) currently inspect `tool_input.file_path` and `tool_input.content`. On Codex, their input is the `apply_patch` envelope — they must parse the `*** Update File: <path>` header and the `+`/`-` hunks instead.

---

## 4. MCP implementation differences

### 4.1 Transport

Both Claude Code and Codex support **stdio MCP** as the primary transport. Codex additionally supports HTTP via `experimental_use_rmcp_client = true` ([source](https://developers.openai.com/codex/mcp)).

ALIVE's MCP server uses stdio. Portable.

### 4.2 Configuration format

| Claude Code | Codex |
|---|---|
| `.mcp.json` with `mcpServers` object | `config.toml` with `[mcp_servers.<name>]` tables, OR `.mcp.json` referenced from `plugin.json` |
| `{ "command": "...", "args": [...], "env": {...} }` | Same fields, TOML syntax |

Our current `/Users/benflint/aliveplugindev/codex/.mcp.json` works because Codex plugin.json points to it via `"mcpServers": "./.mcp.json"`. Good.

### 4.3 Known bugs

- Issue [#3441](https://github.com/openai/codex/issues/3441) — Codex ignoring MCP servers defined in config.toml in some cases. Watch list, not blocker for plugin-scoped MCP.
- Codex has a **startup_timeout_sec** (default 10) and **tool_timeout_sec** (default 60) that don't exist in Claude Code. Our Python MCP server boots fast but if it ever pulls in heavy deps, we need to bump these.

### 4.4 Protocol version

Both clients implement MCP 1.x spec. No known protocol-level incompatibilities with a well-formed Python MCP server.

### 4.5 Tool parameter schemas

JSON Schema. No meaningful difference. Codex does slightly stricter validation on `required` fields than Claude — servers that lazily omit declared-but-optional fields will get clearer error messages from Codex.

---

## 5. Plugin and skill loading

### 5.1 Plugin structure

| | Claude Code | Codex |
|---|---|---|
| Manifest dir | `.claude-plugin/` | `.codex-plugin/` |
| Manifest | `plugin.json` | `plugin.json` |
| Skills dir | `skills/` | `skills/` (pointed to by `"skills": "./skills/"`) |
| MCP | `hooks.json`, or ambient | `.mcp.json` (pointed to by `"mcpServers": "./.mcp.json"`) |
| Apps/connectors | N/A | `.app.json` |
| Hooks | `hooks/hooks.json` | `hooks/hooks.json` (when `codex_hooks` flag on) |
| Rules | `CLAUDE.md` | `AGENTS.md` |
| Install cache | `~/.claude/plugins/` | `~/.codex/plugins/cache/$MARKETPLACE/$PLUGIN/$VERSION/` |

**Score:** Directory layout is nearly identical. Our `/Users/benflint/aliveplugindev/codex/.codex-plugin/plugin.json` already follows this.

### 5.2 Skill discovery

| | Claude Code | Codex |
|---|---|---|
| Load model | All skill metadata pre-loaded | **Lazy metadata** — only name + description at startup, full SKILL.md loaded on trigger ([source](https://developers.openai.com/codex/skills)) |
| Explicit invocation | `/skill-name` | `$skill-name` or `/skills` browser |
| Implicit invocation | Matching by description | Matching by description; **togglable via `allow_implicit_invocation: false`** in `agents/openai.yaml` |
| Skill persistence | Carries across turns | **Does not persist across turns unless re-mentioned** ([source](https://blog.fsck.com/2025/12/19/codex-skills/)) |
| Browser | `/agents` command | `/skills` or `$skill-installer` |

**Critical:** Codex skills **reset per turn.** If the save skill is invoked on turn 5, by turn 6 Codex is no longer "in save mode" unless the skill content is re-injected. This breaks ALIVE's assumption that, e.g., alive-boot-sequence stays active for the whole session.

**Mitigation:** boot-sequence behaviour must move into AGENTS.md (persistent) rather than being a skill (transient on Codex).

### 5.3 Rule file size

Codex: hard 32 KiB cap per AGENTS.md file, extensible via nested files. ALIVE README claims 28 KiB current. Room, but thin.

Claude Code: no published cap; large CLAUDE.md files degrade quality but aren't truncated.

---

## 6. Context window behaviour

### 6.1 Compaction

| | Claude Code | Codex |
|---|---|---|
| Manual | `/compact` | `/compact` |
| Auto trigger | ~95% context | `model_auto_compact_token_limit` (default ~95%) |
| Hook | `PreCompact` fires | **No PreCompact** |
| State loss | Partial (recent messages retained) | **Documented mid-task context loss** ([#5957](https://github.com/openai/codex/issues/5957)) |
| Summary framing | "what's accomplished, next steps" | "handoff to another LLM" |
| Known issues | Can "go off rails" | Auto-compact never-finishing bug ([community thread](https://community.openai.com/t/auto-compression-not-triggering-codex-still-runs-out-of-context-window/1376334)) |

Source: [Context compaction research gist](https://gist.github.com/badlogic/cd2ef65b0697c4dbe2d13fbecb0a0a5f).

### 6.2 GPT-5.1-Codex-Max

The newer Max variant does "automatic session compaction" — it compacts itself and continues the task within one invocation, repeating until done ([source](https://openai.com/index/gpt-5-1-codex-max/)). This is **not** hook-compatible — the model does it internally, no script runs. For ALIVE this means Max users get even less observability into compaction than base GPT-5-Codex users.

### 6.3 Zero-context standard

ALIVE's "zero-context standard" (each session starts with zero assumed context and rebuilds from `_squirrels/`) **holds on Codex** — in fact it's more important, because Codex has no cross-session memory and the instruction chain is rebuilt every run ([source](https://developers.openai.com/codex/guides/agents-md)). Our assumption is safe.

**But:** the standard assumes the rebuild step executes reliably at session start. On Codex, `SessionStart` fires (good), but the **rebuild skill** may not stay loaded for the turn (skills reset, §5.2). Fix: put the rebuild instructions in AGENTS.md, not a skill.

---

## 7. Config system

### 7.1 Where config lives

| | Claude Code | Codex |
|---|---|---|
| Per-user | `~/.claude/settings.json` | `~/.codex/config.toml` |
| Per-project | `.claude/settings.json` | `.codex/config.toml` (trusted projects only) |
| Format | JSON | TOML |

### 7.2 Keys that differ

Codex exposes *more* tunables than Claude on some axes and *fewer* on others.

**Codex-only (no Claude equivalent):**
- `sandbox_mode` / `approval_policy` / `permissions.*` — strict sandboxing, network rules, filesystem allow-lists
- `model_context_window`, `model_auto_compact_token_limit` — user-tunable compaction
- `profiles.<name>.*` — per-workflow config bundles
- `startup_timeout_sec`, `tool_timeout_sec` for MCP
- `shell_environment_policy.*` — control env inheritance
- `[features] codex_hooks` — hooks feature flag itself

**Claude-only:**
- PreCompact hook config
- Richer matcher regex on PreToolUse/PostToolUse
- Output style system
- Statusline customisation (built-in)
- `SubagentStart` hook

### 7.3 Impact

ALIVE's install docs need a Codex-specific config.toml snippet that:
1. Sets `features.codex_hooks = true`
2. Sets generous `startup_timeout_sec` for the Python MCP
3. Recommends `model_auto_compact_token_limit` at 85% rather than 95% (give the PostToolUse stash time to fire before compaction)
4. Does NOT touch `sandbox_mode` (user's choice)

---

## 8. What's "pretty much a clone" vs what's fundamentally different

### 8.1 Pretty much a clone (mechanical port, <1 day work each)

- `.claude-plugin/plugin.json` → `.codex-plugin/plugin.json` (**done**)
- `CLAUDE.md` → `AGENTS.md` (**done in structure, needs content audit**)
- MCP server registration (**done**)
- `skills/*/SKILL.md` metadata format (Claude uses YAML frontmatter, Codex uses YAML frontmatter — identical)
- Most skill *prose content* (replace "use Read" with neutral verbs)
- `SessionStart`, `UserPromptSubmit`, `Stop` hooks
- Skills: alive-world, alive-capture-context, alive-bundle, alive-session-context-rebuild, alive-create-walnut, alive-build-extensions, alive-boot-sequence, alive-settings, alive-system-cleanup, alive-system-upgrade, alive-my-context-graph

### 8.2 Fundamentally different (needs real design work)

- **PreCompact replacement** — no direct analogue. Must redesign stash flushing around PostToolUse (see §2.4).
- **Guardian hooks** — `log-guardian`, `rules-guardian`, `root-guardian`, `archive-enforcer` all inspect tool_input fields that don't exist in Codex. They need to parse `apply_patch` diffs instead. Meaningful code rewrite.
- **External guard** — `alive-external-guard.sh` matches `mcp__.*` tool names in Claude. Codex has no MCP tool matcher at the hook level. Replace with MCP-server-side guard (server itself enforces) or drop.
- **alive-mine-for-context** — relies on WebFetch semantics. Needs a Codex-native replacement via MCP tool or shell+curl+summarise pattern.
- **Save protocol phrasing** — rewrite from Claude's prose style to GPT-5's precondition style (§1.1).
- **Stash persistence model** — move from "model holds stash in conversation" to "stash persisted on every tool-use" (§1.2, §2.4).
- **Squirrel persona** — expect muted inhabitation on GPT-5-Codex; treat squirrel as data structure, not voice (§1.4).
- **Background dispatch** — `alive-background-dispatch.sh` runs on UserPromptSubmit. Portable mechanically, but the boot-sequence-style "always-on cron" model documented in background-crons memory will need its own Codex adaptation because Codex has no SubagentStop event to catch cron completion.
- **Compact-scoped SessionStart matcher** — Codex SessionStart only matches `startup` and `resume`, not `compact`. `alive-session-compact.sh` has no hook to attach to; its work must fold into a PostToolUse stash flush.

---

## What ALIVE needs to adapt

Concrete, prioritised checklist for the Codex port:

### P0 — blocking the first working Codex release

1. **Rewrite all 4 file-mutation guardian scripts** to parse `apply_patch` envelope instead of `tool_input.file_path`/`tool_input.content`. Scripts: `alive-log-guardian.sh`, `alive-rules-guardian.sh`, `alive-root-guardian.sh`, `alive-archive-enforcer.sh`, `alive-post-write.sh`, `alive-inbox-check.sh`.
2. **Drop `PreCompact` hook entirely** on Codex side; document as "known limitation, manual /save required before compaction" until mitigation in P1.
3. **Drop `alive-session-compact.sh`** (no matcher); fold its repo-redetect behaviour into `alive-repo-detect.sh` called from `alive-post-write.sh` on a staleness check.
4. **Drop `alive-external-guard.sh`** or move its logic server-side into the MCP server itself.
5. **Audit AGENTS.md for 32 KiB cap.** Currently ~28 KiB per README claim. Split into `AGENTS.md` + `.alive/AGENTS.md` if headroom needed.
6. **Move boot-sequence instructions from skill to AGENTS.md** — skills don't persist across turns on Codex (§5.2).
7. **Add install-doc step:** user must set `features.codex_hooks = true` in `~/.codex/config.toml`.

### P1 — critical for parity

8. **Persist stash on every PostToolUse.** New script or extend `alive-post-write.sh`. Eliminates dependence on model-held conversation state (§1.2).
9. **Rewrite save protocol phrasing** — convert prose narrative to precondition checklist style. Target files: `skills/alive-save/SKILL.md`, `skills/alive-load-context/SKILL.md`, `skills/alive-session-context-rebuild/SKILL.md`.
10. **Build Codex-native `alive-mine-for-context`** — add MCP tool `mine_url(url: str) -> markdown` so the skill doesn't depend on WebFetch.
11. **Add config.toml recommendations doc:** suggest `model_auto_compact_token_limit = 0.85 * context_window` to give PostToolUse stash flushing time to fire before compaction.
12. **Statusline / output-style equivalent** — investigate Codex `personality` and `agents/openai.yaml` for UI metadata; accept that we lose full statusline control.

### P2 — nice-to-have, polish

13. **Lean out squirrel persona prose** — GPT-5-Codex doesn't inhabit personas like Claude does. Cut voice, keep structure.
14. **Add `allow_implicit_invocation: false`** to highest-stakes skills (alive-save, alive-create-walnut) so GPT-5 doesn't trigger them inadvertently.
15. **File upstream issues** with OpenAI: PreCompact hook, regex matchers on PreToolUse beyond Bash/apply_patch, SubagentStart/Stop events.
16. **Contribute `PreCompact` to Codex** if upstream is slow. OpenAI's hooks system is marked "under development" — this is the moment to land the feature we need.

---

## Sources

- [Codex Hooks docs](https://developers.openai.com/codex/hooks) — primary source on hook events
- [Codex Skills docs](https://developers.openai.com/codex/skills) — skill structure and loading model
- [Codex Plugins docs](https://developers.openai.com/codex/plugins) — plugin installation
- [Codex Build Plugins docs](https://developers.openai.com/codex/plugins/build) — plugin.json schema
- [Codex AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md) — rule-file handling and 32 KiB cap
- [Codex MCP docs](https://developers.openai.com/codex/mcp) — stdio transport
- [Codex config reference](https://developers.openai.com/codex/config-reference) — config.toml keys
- [Codex advanced config](https://developers.openai.com/codex/config-advanced) — codex_hooks feature flag
- [Codex Subagents docs](https://developers.openai.com/codex/subagents)
- [Codex Customization](https://developers.openai.com/codex/concepts/customization)
- [GitHub #12208 — PreCompact request](https://github.com/openai/codex/issues/12208)
- [GitHub #5957 — auto compact loses plot](https://github.com/openai/codex/issues/5957)
- [GitHub #3441 — MCP servers ignored](https://github.com/openai/codex/issues/3441)
- [Claude Code hooks docs](https://code.claude.com/docs/en/hooks)
- [Context compaction research gist (Claude/Codex/OpenCode/Amp)](https://gist.github.com/badlogic/cd2ef65b0697c4dbe2d13fbecb0a0a5f)
- [Codex skills behavioural analysis](https://blog.fsck.com/2025/12/19/codex-skills/)
- [Plugins system deepwiki](https://deepwiki.com/openai/codex/5.11-plugins-system)
- [Claude Sonnet 4.5 vs GPT-5 instruction following](https://portkey.ai/blog/claude-sonnet-4-5-vs-gpt-5/)
- [GPT-5.4 vs Claude Opus 4.6 comparison](https://www.mindstudio.ai/blog/gpt-5-4-vs-claude-opus-4-6-comparison)
- [Codex vs Claude Code architecture deep dive](https://blakecrosley.com/blog/codex-vs-claude-code-2026)
- [OpenAI GPT-5 sycophancy reduction](https://openai.com/index/introducing-gpt-5/)
- [Mob rule and sycophancy forum thread](https://community.openai.com/t/mob-rule-and-sycophancy-gpt-5-and-chatgpt/1347904)
- [Role-prompting research](https://www.prompthub.us/blog/role-prompting-does-adding-personas-to-your-prompts-really-make-a-difference)
- [GPT-5.1-Codex-Max announcement](https://openai.com/index/gpt-5-1-codex-max/)
- [How OpenAI Codex works vs Claude Code](https://blog.promptlayer.com/how-openai-codex-works-behind-the-scenes-and-how-it-compares-to-claude-code/)

### Guesses (explicitly flagged)

- **Sycophancy in ALIVE context**: extrapolated from OpenAI's own sycophancy evals to ALIVE-specific failure modes. Not tested. Guess.
- **Persona resistance**: based on general research; not tested with the squirrel persona specifically. Guess.
- **Unicode box-drawing drift**: 10% drift figure is estimated, not measured. Guess.
- **Stash-on-every-PostToolUse overhead**: flagged as a solution; real-world token cost unmeasured. Guess.
- **32 KiB AGENTS.md headroom**: README claim of 28 KiB is unverified by this document. Measure the actual file.
- **GPT-5.1-Codex-Max self-compaction being hook-invisible**: inferred from the announcement copy; not directly confirmed. Guess.
