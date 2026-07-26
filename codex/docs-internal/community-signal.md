# Codex Community Signal — Pain Points, Wins, Gotchas

Mined from `github.com/openai/codex` issues + discussions, the OpenAI Developer Community forum, HN, and READMEs of popular community plugins. Every claim is URL-backed. Compiled 2026-04-17.

---

## Top 10 Complaints / Pain Points (Ranked by Evidence)

### 1. Manual `/compact` removed / missing in the App — 145 upvotes, 53 comments
- OpenAI's position: "we've implemented a robust auto compaction mechanism, so there should no longer be a need for developers to manage context windows manually… our goal is to eventually remove it." — `etraut-openai` on [issue #11325](https://github.com/openai/codex/issues/11325).
- The thread became a multi-page revolt. Representative quotes:
  - "the robust auto compaction mechanism doesn't work for me. When the context gets close to 258k but not close enough the auto compaction fails with this error." — `MrRobot701`
  - "removing it is a bad design choice, there are plenty of times where I compact context before moving to the next task." — `rickycambrian`
  - "I find myself opening the session in CLI just to run compact and going back to the App. Very frustrating." — `archiboi69`
- Related: [#14346 Context Compaction Hanging (19 up)](https://github.com/openai/codex/issues/14346), [#14860 Error running remote compact task (23 up)](https://github.com/openai/codex/issues/14860), [#13279 Compaction death spiral](https://github.com/openai/codex/issues/13279), [#14347 Extend compaction prompt to reduce loss](https://github.com/openai/codex/issues/14347).
- **Signal:** Users do not trust auto-compaction and hate having control taken away. Anything ALIVE does around session state needs to survive and cooperate with Codex's compaction — not assume it works.

### 2. AGENTS.md silently truncated at 32 KB
- [#13386 AGENTS.md is silently truncated and instructions near the end ignored](https://github.com/openai/codex/issues/13386): "Codex silently truncates `AGENTS.md` at `32 KB` (roughly 600–800 lines). Any instructions past that limit are dropped and never sent to the model - with no warning anywhere in the TUI, /stats, exec, or VS Code extension."
- Still referenced as active: `guidedways` in [#6038](https://github.com/openai/codex/issues/6038) — "codex internally has a hard limit (configurable, thankfully) where it will simply truncate and not read anything more than 32kb."
- Related: [#14687 silently fails loading global AGENTS.md on encoding issues](https://github.com/openai/codex/issues/14687), [#17498](https://github.com/openai/codex/issues/17498) + [#17781](https://github.com/openai/codex/issues/17781) + [#17510](https://github.com/openai/codex/issues/17510) (all `Agents.md: <none>` shown even when loaded).
- **Signal:** Any ALIVE kernel or manifest shipped through `AGENTS.md` must stay well under 32 KB, place critical instructions at the TOP, and verify attachment at runtime. Don't trust the status line.

### 3. Compaction bugs stacked — 23+19+5+5 upvotes
- [#14860 Error running remote compact task (23 up, 35 comments)](https://github.com/openai/codex/issues/14860)
- [#14346 Context Compaction Hanging (19 up, 20 comments)](https://github.com/openai/codex/issues/14346)
- [#14342 Compacting is getting stuck](https://github.com/openai/codex/issues/14342)
- [#14913 Compaction error](https://github.com/openai/codex/issues/14913)
- [#14425 Compaction hangs indefinitely at <16%](https://github.com/openai/codex/issues/14425)
- [#11440 Repeated 413 errors on compaction](https://github.com/openai/codex/issues/11440)
- **Signal:** Compaction is the #1 functional bug in Codex today. ALIVE should treat it as a hostile runtime — rehydration after compaction failure is a feature, not a nicety.

### 4. MCP server lifecycle is leaky — zombies, 37 GB leaks, exhausted threads
- [#12491 1300+ zombies, 37GB memory leak](https://github.com/openai/codex/issues/12491)
- [#14548 Codex spawning too many mcp instances and never kills them](https://github.com/openai/codex/issues/14548)
- [#11324 MCP servers eat up memory when multi-tasking](https://github.com/openai/codex/issues/11324)
- [#17574 Subagents leak stdio MCP helper trees](https://github.com/openai/codex/issues/17574)
- `gabrielbryk` on Linux 0.106.0: "A single long-running codex session accumulated 41 zombie `<defunct>` children… codex parent never calls `waitpid()` to reap them."
- **Signal:** Do NOT ship MCP servers as the default distribution for ALIVE context. If you must, make them explicitly long-lived singletons, not spawned per-session.

### 5. Plugin-local hooks are documented but don't execute — "docs lie"
- [#16430 Plugin docs/examples imply plugin-local hooks, but runtime only executes global hooks.json](https://github.com/openai/codex/issues/16430)
- [#17331 Plugin manifests define `hooks`, but plugin hooks are not loaded into the Codex hooks runtime](https://github.com/openai/codex/issues/17331) — closed as dup of 16430.
- [#16466 Hooks should support stable bundle/plugin context for reusable hook scripts](https://github.com/openai/codex/issues/16466). `andre-menutole`: "plugins already act as a packaging/composition boundary… `hooks` look like a missing runtime capability in the same composition model."
- **Signal:** If ALIVE needs hooks, plan for the user to install them into `~/.codex/hooks.json` manually (or via a post-install script). Expect plugin-local hooks to be broken for months.

### 6. Hooks only fire for Bash — ApplyPatch and others silently skipped — 10 upvotes
- [#16732 ApplyPatchHandler doesn't emit PreToolUse/PostToolUse hook event. Hooks only fire for Bash tool.](https://github.com/openai/codex/issues/16732)
- `horiacristescu`: "Please implement the ApplyPatchHandler/FileEdit hooks, my harness depends on them to enforce workflow discipline. I can't find a workaround."
- Related: [#16246 PostToolUse missing for tools completing via exec/polling](https://github.com/openai/codex/issues/16246), [#18067 Codex CLI hooks fail silently on Linux/Windows when editing large files](https://github.com/openai/codex/issues/18067).
- `aashish-thapa` pinpointed root cause: `hook_runtime.rs` hardcodes `tool_name: "Bash"`; `ApplyPatchHandler` has no payload methods.
- **Signal:** If ALIVE wants to react to file writes, shell intercepts are the only reliable channel today. Don't build on PreToolUse for non-shell tools.

### 7. Hooks don't fire in interactive sessions from repo-local config
- [#17532 codex_hooks do not fire in interactive sessions when configured via repo-local .codex/config.toml](https://github.com/openai/codex/issues/17532)
- `abhinav-oai` (OpenAI): "We don't support a custom path to a `hooks.json` via top-level `hooks` field in the `config.toml`. Codex will resolve the `hooks.json` by looking in the same directories as any enabled config layers."
- **Signal:** Hook location resolution is undocumented and surprising. Use `.codex/hooks.json` (co-located with config) and require `features.codex_hooks = true` in a config layer — not a custom `[hooks]` block.

### 8. Plugin startup sync fails on Cloudflare challenge, plugins UI disappears
- [#16543 0.118.0 gets stuck on startup when plugins/featured returns a Cloudflare challenge page](https://github.com/openai/codex/issues/16543)
- [#16808 Codex desktop plugin marketplace unreachable — Cloudflare challenge blocks plugins/featured API](https://github.com/openai/codex/issues/16808)
- [#16006 Codex App briefly shows 'New Plugin' then falls back to 'Skills' after startup (5 up, 11 comments)](https://github.com/openai/codex/issues/16006): `kilwizac` traced it to Cloudflare 403s on `/backend-api/plugins/list` and `/featured`.
- [#16004 Curated plugin startup sync leaks `~/.codex/.tmp/plugins-clone-*` directories on failure](https://github.com/openai/codex/issues/16004)
- [#16637 Panic: plugin cache root resolution fails when running in a git worktree](https://github.com/openai/codex/issues/16637)
- [#17066 Marketplace local plugin path `./` cannot reference the repository root](https://github.com/openai/codex/issues/17066)
- Workaround users discover: add `[features]\nplugins = true` to `~/.codex/config.toml` manually ([#15962 comments](https://github.com/openai/codex/issues/15962)).
- **Signal:** Installation is fragile. Ship a single bash/pwsh bootstrapper that (a) writes the feature flag, (b) installs as local marketplace path, (c) verifies. Do NOT assume remote marketplace sync works.

### 9. AGENTS.md + developer_instructions injection bugs
- [#11004 Codex App: developer_instructions (config.toml) are not attached to threads initiated within the App (8 up)](https://github.com/openai/codex/issues/11004) — still open, still a bug.
- [#7973 experimental_instructions_file - not working the slightest](https://github.com/openai/codex/issues/7973)
- [#17498 /status shows Agents.md: <none> even when AGENTS.md exists and appears to be loaded (8 up, closed)](https://github.com/openai/codex/issues/17498)
- `Takhoffman`: "Repo AGENTS.md are loaded in as developer role instructions often overruling my custom instructions… I think a better approach is to let the user choose what role they come in as."
- **Signal:** The role (developer vs user) of injected context matters. If ALIVE instructions come in as user messages they'll lose every fight with a repo AGENTS.md.

### 10. Nested AGENTS.md / `@include` not supported — 27+16 upvotes
- [#12115 Dynamically loading nested AGENTS.md (27 up, 9 comments)](https://github.com/openai/codex/issues/12115). `miraclebakelaser`: "auto context hydration is a low-hanging fruit… it's also part of the AGENTS.md standard."
- [#6038 Ability to include files in AGENTS.md (16 up)](https://github.com/openai/codex/issues/6038)
- [#17401 `@include` directive for composable AGENTS.md files](https://github.com/openai/codex/issues/17401) — `MOlechowski` already has a PR matching Claude/Gemini/Cursor/Amp's `@path` syntax.
- **Signal:** Every coding-agent CLI except Codex has composable instruction files. ALIVE's manifest/bundle model IS the workaround — position it as such.

### Honorable mentions
- [#8925 Feature request: Support for plugin marketplaces (34 up)](https://github.com/openai/codex/issues/8925). `PaulRBerg` proposed: "just look at `~/.claude/plugins`."
- [#9266 Add mcp search tool, lazy mcp load (21 up)](https://github.com/openai/codex/issues/9266). A fork ([xCodex](https://github.com/Eriz1818/xCodex)) shipped lazy MCP loading before upstream because context pollution from MCP tool schemas is severe.
- [#16083 Disable the built-in GitHub app after v0.117 (8 up, 9 comments)](https://github.com/openai/codex/issues/16083): 50+ GitHub tool schemas auto-loaded even for users who don't use GitHub. `milanglacier`: "Do you think it's a good idea to blindly load so many tool schemas into the context window at startup, with no option to disable them?"
- [#16127 yeet skill is over opinionated (4 up, 7 comments)](https://github.com/openai/codex/issues/16127): built-in skills can't be disabled without AGENTS.md workarounds; users resort to "Don't use the github:yeet skill."
- [#9198 resuming codex with session-id will lose some information (4 up, 15 comments)](https://github.com/openai/codex/issues/9198): session resume is lossy, especially after compaction.
- [#16226 Hooks: distinguish subagent events from main agent](https://github.com/openai/codex/issues/16226): no way to filter hooks by main vs subagent.
- [#17588 Config/profile disables for connectors, apps, and plugins are ignored](https://github.com/openai/codex/issues/17588): `etraut-openai` confirms "Profiles do not currently support arbitrary nested config sections like `mcp_servers`, `apps`, or `plugins`" — replacement planned.
- [#13186 Codex usage metering anomaly (very small tasks consuming large quota)](https://github.com/openai/codex/issues/13186): relevant because plugins inflate context and thus token cost.

---

## What Existing Plugins Do Well (Steal This)

### A. AgentOps — closest peer
- [boshu2/agentops](https://github.com/boshu2/agentops): "DevOps layer for coding agents with flow, feedback, and memory that compounds between sessions."
- Winning moves:
  - Multi-agent install (Claude Code + Codex + OpenCode) via separate bootstrappers — one curl script per runtime, no relying on Codex's broken marketplace.
  - `.agents/` directory for bookkeeping — local-first, reversible.
  - Optional CLI companion (`ao`) — plugin + shipped binary. `ao doctor` for diagnostics, `ao demo` for onboarding proof.
  - Explicit "what it touches" table in README — permission surface, network behavior, reversibility. Users fear plugins; transparency buys trust.
- **Steal:** the reversibility + diagnostics pattern. Add `alive doctor`.

### B. Codex-Mem — persistent memory compression (ALIVE's adjacent space)
- [2kDarki/codex-mem](https://github.com/2kDarki/codex-mem) (fork of `thedotmack/claude-mem`).
- Architecture:
  - 5 lifecycle hooks — SessionStart, UserPromptSubmit, PostToolUse, Stop, SessionEnd.
  - Worker service on port 37777 with web UI + 10 search endpoints, managed by Bun. Keeps UI out of Codex.
  - SQLite + FTS5 for storage; Chroma for hybrid vector + keyword search.
  - MCP surface with 3-layer workflow: `search` (index, ~50-100 tok/result) → `timeline` (chronological context) → `get_observations` (full fetch only for filtered IDs). Claims ~10× token savings by "filter before fetch."
- **Steal:** the 3-layer progressive-disclosure MCP pattern. This is what ALIVE's subagent brief hints at but doesn't formalize. Also: separate worker process for UI, not in-Codex UI.

### C. Session Orchestrator — cross-runtime bundle
- [Kanevry/session-orchestrator](https://github.com/Kanevry/session-orchestrator): "No runtime code. Pure Markdown." Works across Claude/Codex/Cursor via a `platform.sh` abstraction.
- README's compatibility matrix ("Claude Code has PreToolUse hooks, Codex hooks are experimental, Cursor is post-hoc only") is gold — honest about each runtime's limits.
- **Steal:** the cross-runtime compatibility matrix. If ALIVE supports Claude + Codex, publish the matrix prominently.

### D. awesome-codex-plugins (HOL) — the curation + trust layer
- [hashgraph-online/awesome-codex-plugins](https://github.com/hashgraph-online/awesome-codex-plugins) is the de facto list — 12 official + ~50 community plugins, 71 stars.
- All entries scanner-verified via [hashgraph-online/ai-plugin-scanner](https://github.com/hashgraph-online/ai-plugin-scanner) (formerly `codex-plugin-scanner`). Trust badges, CI gates, SARIF output.
- Submission = PR + optional `plugin-scanner` verify. Repo-level `.agents/plugins/marketplace.json` acts as local marketplace source.
- **Steal:** get listed there day 1. Run the scanner. Embed the trust badge.

### E. Awesome Codex CLI — broader ecosystem list
- [RoggeOhta/awesome-codex-cli](https://github.com/RoggeOhta/awesome-codex-cli): 280+ resources, 20 categories including "Cross-Agent Tools," comparison table with Claude Code + Gemini CLI. Target this list too.

---

## Common Build Gotchas That Broke Other Plugins

1. **Plugin-local hooks in `.codex-plugin/plugin.json` do not execute.** Runtime only reads `~/.codex/hooks.json` + workspace `.codex/hooks.json`. ([#16430](https://github.com/openai/codex/issues/16430))
2. **Hooks only fire for the Bash tool.** ApplyPatch, MCP tools, Write, WebSearch are silently skipped. ([#16732](https://github.com/openai/codex/issues/16732), [developers.openai.com/codex/hooks](https://developers.openai.com/codex/hooks))
3. **`features.codex_hooks = true` is required and not obvious** — hooks will simply never fire without it. ([#17532](https://github.com/openai/codex/issues/17532))
4. **Plugins UI is gated behind `[features].plugins = true` in `~/.codex/config.toml`.** If the install script doesn't write it, users see "Skills" instead. ([#15962](https://github.com/openai/codex/issues/15962), [#16006](https://github.com/openai/codex/issues/16006))
5. **Remote plugin sync is blocked by Cloudflare challenges** for users behind VPNs/corp proxies. Local marketplace always works; trust that. ([#16543](https://github.com/openai/codex/issues/16543), [#16808](https://github.com/openai/codex/issues/16808))
6. **Plugin cache panics in git worktrees.** ([#16637](https://github.com/openai/codex/issues/16637))
7. **Marketplace local path `./` doesn't resolve to repo root.** Use explicit relative paths. ([#17066](https://github.com/openai/codex/issues/17066))
8. **SKILL.md frontmatter must be valid strict YAML, no BOM.** Invalid YAML silently drops the skill. ([#13918](https://github.com/openai/codex/issues/13918), [#14785](https://github.com/openai/codex/issues/14785))
9. **Skills show duplicates across scopes with no precedence indicator.** ([#9930](https://github.com/openai/codex/issues/9930))
10. **Resumed threads keep stale model-visible skills** — a newly added skill is not visible to a resumed session. ([#16607](https://github.com/openai/codex/issues/16607), [#11710](https://github.com/openai/codex/issues/11710))
11. **`skill-creator` scaffolds things that don't exist** — references `package_skill.py` which isn't shipped, confusing the agent. ([#10264](https://github.com/openai/codex/issues/10264), [#10736](https://github.com/openai/codex/issues/10736))
12. **Codex Desktop creates project skills in `$(pwd)/skills`, not the expected project-local scope.** ([#10424](https://github.com/openai/codex/issues/10424), [#15304](https://github.com/openai/codex/issues/15304))
13. **MCP stdio servers are not reaped on session end** — zombies unless you handle SIGTERM yourself. ([#12491](https://github.com/openai/codex/issues/12491), [#14548](https://github.com/openai/codex/issues/14548))
14. **MCP tool schemas pollute context at startup** — 50+ GitHub tools loaded even for non-GitHub users. Keep your MCP tool count small. ([#16083](https://github.com/openai/codex/issues/16083), [#9266](https://github.com/openai/codex/issues/9266))
15. **Built-in skills can't be disabled via config** — only talked-out-of via AGENTS.md hints. Your plugin will compete with `github:yeet` etc. ([#14316](https://github.com/openai/codex/issues/14316), [#16127](https://github.com/openai/codex/issues/16127))
16. **Profiles don't support `mcp_servers`, `apps`, `plugins` sections** — nested config in profiles is ignored. ([#17588](https://github.com/openai/codex/issues/17588))
17. **WSL resume restores lowercased cwd** — path casing matters. ([#14257](https://github.com/openai/codex/issues/14257))
18. **Windows: Plus accounts show only Skills, Free accounts show Plugins.** Plan-tier-dependent UI. ([#16903](https://github.com/openai/codex/issues/16903))
19. **Session ID can be printed but no rollout artifact persisted** after transport failure — `codex resume` breaks. ([#15870](https://github.com/openai/codex/issues/15870))
20. **Hook `additionalContext` is rendered as a visible developer message** — don't treat it as invisible. ([#16933](https://github.com/openai/codex/issues/16933))

---

## The Wishlist — Features Users Keep Asking For (The Opportunity)

### W1. Durable cross-session memory that survives compaction — HIGHEST DEMAND
- [Discussion #15432 Thread-Scoped Session Memory Layer Over Compaction](https://github.com/openai/codex/discussions/15432) proposes a `SessionMemoryService` with BM25 retrieval, per-turn auto-recall capsules, and a hidden `session_memory_recall` tool. Full design doc exists.
- [Discussion #14067 Synchronization of Codex Threads and Session Context Across Devices (14 up)](https://github.com/openai/codex/discussions/14067): "For users who frequently switch between machines, this would make Codex feel like a persistent development partner rather than a tool that resets context when changing devices."
- `ignatremizov` on [#11325](https://github.com/openai/codex/issues/11325): "the maintainers are working on a SQL-backed memory system, still under development. Best sharing of context cross-thread is via AGENTS.md and SKILL.md files, or my preferred method recently, spec-kit files."
- **ALIVE opportunity:** this IS the product. PCM category already lives here.

### W2. PreCompact / PostCompact / SessionEnd hooks
- [#11912 give us a hook for custom compaction (4 up)](https://github.com/openai/codex/issues/11912). `QIANSUIMINGMINGMING` nails the ALIVE use case: "a deterministic hook immediately before compaction… I keep durable project state in `.agent-doc/`… the exact feature that would solve this for me is something like a `PreCompact` hook with payload fields such as cwd, session_id, thread_id, reason (auto vs manual), current context/token usage."
- [#17148 Pre and PostCompact hooks](https://github.com/openai/codex/issues/17148)
- [#17421 Add SessionEnd hook (closed as dup)](https://github.com/openai/codex/issues/17421), [#17333 Add TaskCompleted Hook Event](https://github.com/openai/codex/issues/17333)
- **ALIVE opportunity:** ship without these by using `Stop` + periodic `UserPromptSubmit` + time-based worker. Document the limitation and workaround.

### W3. Hot-reload hooks + subagent-aware hooks + skill hooks
- [#17636 Hot-reload hook configuration during a live session](https://github.com/openai/codex/issues/17636)
- [#16226 Hooks: distinguish subagent events from main agent](https://github.com/openai/codex/issues/16226)
- [#17132 Add PreSkillUse and PostSkillUse hooks](https://github.com/openai/codex/issues/17132)

### W4. Multi-dir context (`--add-dir`), cross-worktree thread sync
- [docs.bswen.com Codex App missing features](https://docs.bswen.com/blog/2026-03-13-codex-app-missing-features/): "until they support `--add-dir` equivalent it only works on half of my use cases."
- [Discussion #16440 Agent-created worktrees should sync with thread](https://github.com/openai/codex/discussions/16440)

### W5. Per-skill model selection
- [Discussion #13824 Support model selection per skill (6 up)](https://github.com/openai/codex/discussions/13824): "search/research skills → smaller, faster model; implementation/debugging → stronger model."

### W6. Plugin CLI (`codex plugins ...`) and editable install
- [#17431 Add `codex plugins` CLI subcommand for plugin management](https://github.com/openai/codex/issues/17431)
- [#16252 Editable plugin installation](https://github.com/openai/codex/issues/16252): no `--editable` install today; devs manually symlink.
- **ALIVE opportunity:** ship an `alive dev` companion that watches + reloads so authors don't need upstream support.

### W7. Official marketplace submission
- [community.openai.com — How can third-party community plugins be published to the Codex marketplace?](https://community.openai.com/t/how-can-third-party-community-plugins-be-published-to-the-codex-marketplace/1377928): no self-serve process. The awesome-codex-plugins list + HOL registry is the best path to discovery today.
- [#8925 Support for plugin marketplaces (34 up)](https://github.com/openai/codex/issues/8925)

### W8. Status line / composer suggestion API
- [#16921 Allow custom status line plugins in Codex CLI](https://github.com/openai/codex/issues/16921)
- [#17341 Expose native composer suggestion hooks/API for local plugins](https://github.com/openai/codex/issues/17341)

### W9. Orchestrator / read-only delegate mode
- [#18105 Add Orchestrator/delegate mode such that the main agent is strictly read-only](https://github.com/openai/codex/issues/18105)

### W10. Context-efficient "Progressive Reading DSL"
- [Discussion #14685 Progressive Reading DSL](https://github.com/openai/codex/discussions/14685) + [#15420 DeCodifier](https://github.com/openai/codex/discussions/15420). Community is actively searching for deterministic low-token workflows. Directly relevant to ALIVE's "research-before-drafting" principle.

---

## Red Flags — Patterns That Get Plugins Criticised or Removed

1. **Over-opinionated built-in skills** ([#16127](https://github.com/openai/codex/issues/16127) — `github:yeet` inserting `codex/` branch prefix and `[codex] ` PR title). Every opinion is a surface for hatred.
2. **Skills with invalid SKILL.md frontmatter** silently disappear ([#13918](https://github.com/openai/codex/issues/13918)). Validate on install. Fail loud.
3. **Plugins that auto-install MCP servers consuming tons of context** ([#16083](https://github.com/openai/codex/issues/16083)). Every tool schema eats context budget.
4. **Plugins that spawn MCP children and don't reap them** ([#12491](https://github.com/openai/codex/issues/12491), [#14548](https://github.com/openai/codex/issues/14548), [#17574](https://github.com/openai/codex/issues/17574)). Memory leaks make users uninstall.
5. **Plugins that register `dangerous_bypass_approval`** or weaken MCP transport — the HOL scanner flags these and gives a low trust score ([ai-plugin-scanner criteria](https://github.com/hashgraph-online/ai-plugin-scanner)).
6. **Plugins distributed via `.env` + `.codex/config.toml` checked into a repo** — recognized attack vector. [Codex RCE vulnerability in CODEX_HOME redirection](https://research.checkpoint.com/2025/openai-codex-cli-command-injection-vulnerability/) (patched in 0.23.0 but the pattern is burned). Never say "clone this repo and run codex."
7. **Secrets in manifests / plugin.json.** Scanner catches hardcoded secrets. Use env vars + documented config.
8. **Paths outside `.agents/plugins/` that bypass marketplace confinement** — scanner flags as path traversal. Keep everything under the plugin dir.
9. **"Install by curl | bash" without a verify step.** AgentOps does this but documents permission surface + reversibility. Without that, users with sec review will skip you.
10. **Unmaintained GitHub Actions (not SHA-pinned)** — scanner penalizes. Pin actions.
11. **Telling users to manually edit `~/.codex/config.toml` `[features]`** — it works but is fragile; write it from your installer (after consent).
12. **Skill names that collide with official plugins** — no precedence resolver means your skill can be silently shadowed ([#9930](https://github.com/openai/codex/issues/9930)).
13. **Dependence on AGENTS.md beyond 32 KB** — silent truncation will bite you. Compress or split across skill files.
14. **Publishing as `codex plugin install` in docs** — no such native CLI. Use the `/plugins` slash command + marketplace add flow or a bootstrap script.

---

## Specific URLs to Monitor

- **Tracking bug for plugin hooks:** [#16430](https://github.com/openai/codex/issues/16430) — fix = unlock plugin-local lifecycle.
- **Tracking bug for compaction hooks:** [#11912](https://github.com/openai/codex/issues/11912) — fix = unlock durable memory.
- **Tracking bug for AGENTS.md truncation:** [#13386](https://github.com/openai/codex/issues/13386) — fix = more room for ALIVE headers.
- **Awesome list to PR on day 1:** [hashgraph-online/awesome-codex-plugins](https://github.com/hashgraph-online/awesome-codex-plugins), also [RoggeOhta/awesome-codex-cli](https://github.com/RoggeOhta/awesome-codex-cli) and [internet-dot/awesome-codex-plugins](https://github.com/internet-dot/awesome-codex-plugins).
- **Scanner to run before shipping:** `pipx run plugin-scanner verify .` + badge embed ([ai-plugin-scanner](https://github.com/hashgraph-online/ai-plugin-scanner)).

---

## TL;DR — Direct Implications for ALIVE Codex Plugin

1. Do NOT rely on plugin-local hooks. Ship a post-install script that writes `~/.codex/hooks.json` with consent.
2. Do NOT rely on PreToolUse for non-Bash tools. Budget around the Bash-only reality.
3. Require `features.codex_hooks = true` AND `features.plugins = true` — set them in install, verify in doctor.
4. Keep AGENTS.md injection under 32 KB and put critical directives FIRST.
5. Ship as a local-marketplace path (repo-level `.agents/plugins/marketplace.json`) — remote sync is unreliable.
6. If you ship MCP servers: singleton + reap on SIGTERM. Budget tool schemas tightly.
7. Cooperate with compaction — don't fight it. Build `Stop` / `UserPromptSubmit` checkpoints that don't assume a PreCompact hook. Log state to disk on every turn.
8. Expose `alive doctor` and `alive demo`. Transparency beats marketing.
9. Get listed + scanner-verified on day 1. Trust score is the UX.
10. Position ALIVE as the user-controlled answer to `/compact` removal — the loudest active grievance in the community.
