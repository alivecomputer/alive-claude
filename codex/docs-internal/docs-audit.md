# Codex CLI Plugin — Docs Audit

**Audit date:** 2026-04-17
**Codex version target:** codex-cli 0.98.0 (installed)
**Latest stable release:** codex-cli 0.121.0 (released 2026-04-15)
**Source plan date:** 2026-04-11 (6 days stale)
**Reviewer:** research-agent pass over official + community sources

> TL;DR verdict: the plan is **mostly correct but has several concrete schema errors**. The plugin manifest has extra fields we invented (`skills_dir`, `hooks`, `mcp`, `rules`) that do not exist; the real field names are `skills`, `mcpServers`, `apps`, `interface`. The skill invocation prefix `$` is still correct but `@` is now the documented-primary. The `apply_patch` matcher for `PreToolUse`/`PostToolUse` is **wrong** — Codex runtime currently only emits `Bash`. MCP `.mcp.json` format with `transport` field is **not documented** — MCP is configured in `config.toml` under `[mcp_servers.<id>]`, not via `.mcp.json` (though `.mcp.json` exists as a plugin-referenced file, its internal schema is undocumented, and `transport` is not a recognised key). AGENTS.md default is confirmed 32 KiB with `project_doc_max_bytes` override. Hooks still require `[features] codex_hooks = true`.

---

## 1. Plugin manifest format

**Plan said:** `.codex-plugin/plugin.json` uses `name, version, description, author, repository, license, keywords, skills_dir, hooks, mcp, rules`.

**Verdict: PARTIALLY WRONG — multiple field names invented.**

Per [Build plugins – Codex | OpenAI Developers](https://developers.openai.com/codex/plugins/build) (authoritative) and confirmed by [hashgraph-online/awesome-codex-plugins](https://github.com/hashgraph-online/awesome-codex-plugins):

**Required fields:**
- `name` (kebab-case identifier)
- `version` (semver)
- `description`

**Optional top-level fields:**
- `author` (object: `{name, email, url}`) — matches plan
- `homepage` (plan missing)
- `repository` — correct
- `license` — correct
- `keywords` — correct
- `skills` — path to skills dir (e.g. `"./skills/"`) — **NOT `skills_dir`**
- `mcpServers` — path to `.mcp.json` — **NOT `mcp`**
- `apps` — path to `.app.json` (plan missing)
- `interface` — object with displayName, shortDescription, longDescription, developerName, category, capabilities, websiteURL, privacyPolicyURL, termsOfServiceURL, defaultPrompt, brandColor, composerIcon, logo, screenshots (plan missing entirely)

**Fields the plan invented that DO NOT exist:**
- `skills_dir` → rename to `skills`
- `hooks` → **not a plugin.json field**. Hooks live in a separate `hooks.json` file discovered next to active config layers (see §3)
- `mcp` → rename to `mcpServers` (which is a *path string*, not an inline object)
- `rules` → **not a known field**

**Fix:** rewrite `.codex-plugin/plugin.json` to drop `skills_dir`, `hooks`, `mcp`, `rules`. Use `skills: "./skills/"`, `mcpServers: "./.mcp.json"`. Consider adding `interface` for marketplace presentation.

---

## 2. Skill format (SKILL.md frontmatter)

**Plan said:** kebab-case `^[a-z0-9-]+$`, description ≤ 1024 chars with no `<` or `>`, no `user-invocable` field.

**Verdict: NAME/DESCRIPTION RULES ARE RIGHT, but two details need correction.**

Per the [Agent Skills Specification at agentskills.io/specification](https://agentskills.io/specification) (the open standard Codex conforms to — linked from [developers.openai.com/codex/skills](https://developers.openai.com/codex/skills)):

**`name` field:**
- 1–64 chars
- lowercase `a-z`, `0-9`, hyphens only
- must NOT start/end with hyphen
- must NOT contain consecutive `--`
- must match parent directory name
- plan regex `^[a-z0-9-]+$` is too permissive — does not guard against leading/trailing/consecutive hyphens. Use: `^[a-z0-9]+(-[a-z0-9]+)*$` and cap length at 64.

**`description` field:**
- 1–1024 chars — correct
- Spec does NOT explicitly forbid `<` / `>` characters. Plan's ban is safe (some client renderers treat descriptions as HTML), but this is not a spec requirement. Keep the rule as a self-imposed safety belt if desired; note it as local policy, not upstream rule.

**`user-invocable` field:** correctly omitted. The spec has no such field. Implicit-invocation control is done via optional `agents/openai.yaml` → `policy.allow_implicit_invocation` (defaults `true`), not in SKILL.md frontmatter.

**Additional optional frontmatter fields the plan does not use (all valid per spec):**
- `license`
- `compatibility` (≤ 500 chars, e.g. `"Designed for Codex CLI"`)
- `metadata` (arbitrary string map — good for `author`, `version`)
- `allowed-tools` (experimental, space-separated pre-approved tools, e.g. `Bash(git:*) Read`)

**Fix:** tighten the name regex; treat the `<`/`>` ban as local policy (document it as such); optionally add `compatibility: Designed for Codex CLI` and `metadata: {author: ..., version: ...}` blocks to each SKILL.md.

---

## 3. Hook events and matchers

**Plan said:** SessionStart `startup`/`resume` (no `compact`); PreToolUse + PostToolUse matcher `apply_patch`; UserPromptSubmit/Stop no matcher.

**Verdict: SessionStart CORRECT. apply_patch is WRONG.**

Per [Hooks – Codex | OpenAI Developers](https://developers.openai.com/codex/hooks):

**Events:** SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop — correct

**Matchers:**

| Event | Matcher behaviour | Current runtime values |
| --- | --- | --- |
| `SessionStart` | regex against source | `startup`, `resume` (combined as `"startup\|resume"` in one matcher) — correct — **no `compact`** |
| `PreToolUse` | regex against tool name | **Only `Bash` is currently emitted.** `apply_patch` is NOT emitted. Doc quote: *"this doesn't intercept MCP, Write, WebSearch, or other non-shell tool calls."* |
| `PostToolUse` | regex against tool name | Same as above — **only `Bash`** |
| `UserPromptSubmit` | matcher ignored — correct |
| `Stop` | matcher ignored — correct |

**Fix:** remove the `apply_patch` matcher from both `PreToolUse` and `PostToolUse` hook entries. If you want to gate on shell-level patch activity, match `Bash` and inspect the command line inside the handler. Track the open issue for broader tool interception but do not rely on it today.

---

## 4. MCP server registration

**Plan said:** `.mcp.json` with `{"mcpServers": {"alive": {"command": "python3", "args": [...], "transport": "stdio"}}}`.

**Verdict: "transport" is WRONG. Structure is plausible but undocumented.**

Per [Codex MCP docs](https://developers.openai.com/codex/mcp) and [config-reference](https://developers.openai.com/codex/config-reference):

- The authoritative, documented way to register MCP servers is in **`config.toml`** under `[mcp_servers.<id>]`, not `.mcp.json`.
- `.mcp.json` is referenced as a plugin-level file (pointed to by `mcpServers` in `plugin.json`) but **its internal schema is not published** in developer docs. Community plugins mirror `config.toml` keys.

**Valid keys for STDIO servers (per `[mcp_servers.<id>]` schema):**
- `command` (required) — correct
- `args` (optional) — correct
- `env` / `env_vars` (optional)
- `cwd` (optional)
- `enabled`, `required`
- `startup_timeout_sec`, `tool_timeout_sec`
- `enabled_tools`, `disabled_tools`
- `supports_parallel_tool_calls`
- `default_tools_approval_mode`, per-tool `approval_mode`

**There is NO `transport` key.** Server type (STDIO vs HTTP) is inferred from which fields are present (`command` → STDIO; `url` → HTTP).

**Fix:** drop `"transport": "stdio"` from `.mcp.json`. Keep `command` + `args`. Consider also adding a `[mcp_servers.alive]` section to the example `config.toml` so users can wire it up manually if their Codex version doesn't auto-load from `.mcp.json`.

---

## 5. Skill invocation

**Plan said:** `$alive-save` in prompts.

**Verdict: CORRECT, but `@` is now the OpenAI-documented primary.**

- [developers.openai.com/codex/plugins](https://developers.openai.com/codex/plugins) says: *"Type `@` to invoke the plugin or one of its bundled skills explicitly."*
- [openai/codex issue #11817](https://github.com/openai/codex/issues/11817) confirms `$<skill>` is functional in the CLI (e.g. `$prd`), while `/<skill>` is not recognised (only `/skills` is a meta-command).
- Both `$skill-name` and `@skill-name` work for explicit invocation today.

**Fix:** no code change. Update user-facing docs to prefer `@alive-save` (the documented form) with `$alive-save` as an alternate. `/skills` is the meta menu.

---

## 6. AGENTS.md behaviour

**Plan said:** default 32 KB, override via `project_doc_max_bytes = 131072`.

**Verdict: CORRECT.**

Per [AGENTS.md guide](https://developers.openai.com/codex/guides/agents-md):
- Default: **32 KiB = 32,768 bytes** — correct
- Config key: `project_doc_max_bytes` — correct (top-level, in `~/.codex/config.toml`)
- `131072` (128 KiB) is a legitimate raised value; plan's override is fine
- Docs note: when the combined instruction file size hits the cap, Codex stops adding further files — you can either raise the cap or split instructions into nested dirs.

No changes needed.

---

## 7. Hook enablement

**Plan said:** `[features] codex_hooks = true` in `config.toml` still required.

**Verdict: CORRECT.**

Per [config-reference](https://developers.openai.com/codex/config-reference) `features.codex_hooks`:
> *"Enable lifecycle hooks loaded from hooks.json (under development; off by default)."*

So yes, hooks remain behind a feature flag as of 0.121.0. Keep the installer guidance that sets this flag.

No changes needed, but flag in install docs that hooks are "under development" — API may still shift.

---

## 8. Plugin discovery / registry

**Plan said:** HOL Plugin Registry (`hashgraph-online/awesome-codex-plugins`) is the main discovery channel; also `openai/codex` discussions #16073.

**Verdict: STILL A discovery channel, no longer THE primary.**

Landscape as of 2026-04-17:

1. **Official marketplace (new, 2026-04-15, v0.121.0):** `codex marketplace add` command now supports GitHub, git URLs, local directories, and direct `marketplace.json` URLs. This is the official in-CLI flow from OpenAI. See [codex v0.121.0 release notes](https://github.com/openai/codex/releases).
2. **[hashgraph-online/awesome-codex-plugins](https://github.com/hashgraph-online/awesome-codex-plugins):** still active (146 commits, GitHub Actions running, scanner tool). Generates `marketplace.json` that feeds local Codex plugin sources and the HOL Plugin Registry at `hol.org/registry/plugins`. Curates official + community plugins with a 6-factor trust score (installability, maintenance, MCP security, plugin security, provenance, publisher quality).
3. **[internet-dot/awesome-codex-plugins](https://github.com/internet-dot/awesome-codex-plugins):** alternative community list announced in [discussion #16073](https://github.com/openai/codex/discussions/16073) on 2026-03-28. Tracks 12 official + 15 community plugins. Less infrastructure than HOL.
4. **[openai/skills](https://github.com/openai/skills):** OpenAI's own Skills Catalog for Codex.

**Recommendation:** list Codex in ALIVE's install docs for all three surfaces:
- Primary: submit to the OpenAI marketplace (the `codex marketplace add` flow) once third-party submissions open (docs say "coming soon").
- Submit PR to hashgraph-online/awesome-codex-plugins (still the richest curated list with trust scoring).
- Cross-post in discussion #16073 / PR to internet-dot list.

---

## Summary of required fixes

| # | Area | Action |
| --- | --- | --- |
| 1 | `plugin.json` | Remove `skills_dir`, `hooks`, `mcp`, `rules`. Add `skills: "./skills/"`, `mcpServers: "./.mcp.json"`, optional `apps`, optional `interface`. |
| 2 | SKILL.md | Tighten name regex to `^[a-z0-9]+(-[a-z0-9]+)*$`. Keep the `<`/`>` ban as local policy, document as such. Optionally add `compatibility` + `metadata`. |
| 3 | Hooks | Remove `apply_patch` matcher from PreToolUse/PostToolUse. Only `Bash` is currently emitted. |
| 4 | `.mcp.json` | Drop `"transport": "stdio"`. Also ship a `config.toml` snippet using `[mcp_servers.alive]` as a fallback wiring method. |
| 5 | Invocation docs | Prefer `@alive-save`; list `$alive-save` as alt. Do NOT document `/alive-save`. |
| 6 | AGENTS.md | No change. `project_doc_max_bytes = 131072` override is correct. |
| 7 | `config.toml` | No change. Keep `[features] codex_hooks = true` in install docs. |
| 8 | Registry | Add pointer to `codex marketplace add` (official, v0.121.0+). Still submit to hashgraph-online/awesome-codex-plugins. |

---

## Sources

All checks performed 2026-04-17.

- [Build plugins – Codex | OpenAI Developers](https://developers.openai.com/codex/plugins/build)
- [Plugins – Codex | OpenAI Developers](https://developers.openai.com/codex/plugins)
- [Agent Skills – Codex | OpenAI Developers](https://developers.openai.com/codex/skills)
- [Hooks – Codex | OpenAI Developers](https://developers.openai.com/codex/hooks)
- [MCP – Codex | OpenAI Developers](https://developers.openai.com/codex/mcp)
- [Config reference – Codex | OpenAI Developers](https://developers.openai.com/codex/config-reference)
- [AGENTS.md guide – Codex | OpenAI Developers](https://developers.openai.com/codex/guides/agents-md)
- [Changelog – Codex | OpenAI Developers](https://developers.openai.com/codex/changelog)
- [Agent Skills open specification (agentskills.io)](https://agentskills.io/specification)
- [openai/codex GitHub releases](https://github.com/openai/codex/releases) — v0.121.0 (2026-04-15), v0.122.0-alpha.3 (2026-04-16)
- [openai/codex discussion #16073](https://github.com/openai/codex/discussions/16073) — community list announcement (2026-03-28)
- [openai/codex issue #11817](https://github.com/openai/codex/issues/11817) — `$<skill>` vs `/<skill>` invocation
- [hashgraph-online/awesome-codex-plugins](https://github.com/hashgraph-online/awesome-codex-plugins)
- [internet-dot/awesome-codex-plugins](https://github.com/internet-dot/awesome-codex-plugins)
- [openai/skills — Skills Catalog for Codex](https://github.com/openai/skills)
