# ALIVE v3.3 Codex Compatibility Matrix

Tested baseline: macOS, `codex-cli 0.146.0-alpha.3.1`, Python 3.12.12, and
ALIVE MCP 3.3.0. The Codex build itself is an alpha build, so this matrix is a
pinned observation rather than a permanent platform guarantee.

## Guaranteed by explicit ALIVE operations

| Capability | Evidence and boundary |
|---|---|
| Load an existing v3 walnut | The load workflow reads `_kernel/key.md`, `_kernel/now.json`, and `_kernel/insights.md`; package tests reject missing runtime files and checkout-only command paths. |
| Save a decision and task | The explicit save path prepends the log, uses packaged `tasks.py`, and runs `save-refresh.py`: it projects an active walnut, regenerates the world index, explicitly rebuilds orientation, and verifies its fresh strict schema-1 cache renders. Standalone saves skip walnut projection but still refresh the world cache. |
| Recover after a completed save | Two distinct OS processes recovered a unique decision, task, and projected context from disk without reading session-one evidence. The same proof passed on a pruned copy of the real `walnut-world` kernel using runtime scripts from the freshly installed plugin cache. |
| Preserve walnut compatibility | No mandatory schema migration is introduced. The Codex package carries a pinned v3.3 runtime snapshot. Only the approved index serializer and orientation projection are byte-synchronised with `plugins/alive` in this PR; broader Claude/Codex runtime convergence is deferred and no parity claim is made. |
| Read-only MCP discovery | Twelve tools expose walnuts, bundles, tasks, logs, sessions, kernels, and search. Every tool advertises `readOnlyHint: true`, `destructiveHint: false`, and `openWorldHint: false`. A fresh installed process completed MCP initialize and `tools/list`. |
| Native plugin lifecycle management | Install, repeat install, upgrade, doctor, and uninstall pass against a fresh `CODEX_HOME`; uninstall leaves world and unrelated config sentinels unchanged. |
| Current plugin ingestion | The current Codex plugin validator accepts `3.3.0-alpha.3`. Hooks are auto-discovered from `hooks/hooks.json`; the unsupported top-level manifest field is absent and required interface capabilities are declared. |
| Bounded Codex startup orientation | Codex startup hooks render a cached `_orientation.json` projection (at most three recommendations) rather than injecting the full `_index.json`. World and search skills query the complete index only on demand. |
| Repeated-start continuity | Starting the same session twice preserves its loaded walnut, save count, and recovery state. The original beta reset those fields to `none` and `0`; the regression is now covered. |
| Model-backed two-session mechanics | Two separate ephemeral Codex processes used the freshly installed plugin with generated synthetic data and an isolated real walnut copy. Session one saved a decision, task, and projection; session two recovered the exact token without changing the copied kernel. |
| Local private model transport | Codex OSS mode with Ollama `gpt-oss:20b` passed the real-walnut proof and recorded `model_transport: local:ollama` plus `private_context_sent: false`. LM Studio remains harness-supported but unverified. |

## Tested but trust-dependent

| Capability | Limitation |
|---|---|
| Session startup orientation | Runs only when hooks are enabled and the installed hook definition is reviewed/trusted. It finds the world but does not claim that a walnut is loaded. Missing, invalid, unsupported, or stale cached orientation emits a short bounded health notice; startup does not regenerate it. |
| Resume, clear, and compact orientation | `SessionStart` supports all four documented sources. Recovery records contain only state already present in squirrel/walnut files; cached orientation remains bounded rather than a complete world context. |
| Claude adapter baseline | Not part of the alpha.3 Codex claim. Claude hook files are byte-identical to the pre-alpha.3 baseline. That legacy baseline was not evaluated for this release and can inject the full `_index.yaml` plus broader context at session start and prompt thresholds. The shared index serializer is safer, but its default invocation does not build or inject Codex orientation. |
| Pre/post-compaction checkpoint | `PreCompact` and `PostCompact` persist plugin-owned recovery metadata. Developer context is restored through `SessionStart` with source `compact`, because current `PostCompact` output does not provide a documented additional-context field. |
| Post-write projection | Runs synchronously for observed local writes. Hosted and specialized tool paths can bypass tool hooks. |
| Stop record | Updates the squirrel end marker and plugin recovery record when `Stop` fires. An abrupt process kill can bypass it. |
| File guards | Can advise or deny observed local tool calls. Multiple hooks run concurrently, so they are not a complete enforcement or security boundary. |

## Unsupported or not yet proven

- Guaranteed automatic save on every exit, crash, app close, network loss, or
  process kill.
- Observation of every hosted tool or specialized local tool path.
- Claude Code lifecycle parity, Claude settings/statusline mutation, or Claude
  custom-skill symlink behavior.
- A bounded Claude lifecycle or any Claude/Codex hook parity claim. Changing
  Claude injection policy requires separate eval evidence and approval.
- Remote-provider model-backed recovery using private walnut content. The
  minimum-disclosure preflight passed, but the current tenant prohibited
  external disclosure even after user approval; no private content was sent.
- LM Studio and local models other than Ollama `gpt-oss:20b`.
- Windows and Linux support.
- Offline MCP installation.
- Native filesystem-event performance. The private alpha deliberately uses a
  500ms polling observer after the native macOS FSEvents backend crashed during
  repeated sandboxed lifecycle tests; large-World cost is not yet benchmarked.
- Public Codex marketplace acceptance.
- Running v3.3 and the v4 `alivecontext` plugin together. Install and doctor
  fail when another `alive@...` product is enabled in the same profile.
- Production `*.walnut.world`, `user.walnut.world`, seller, payment,
  moderation, or fulfilment services.

## Hook lifecycle facts

- Hooks are enabled by Codex by default but can be disabled with
  `[features].hooks = false`.
- Plugin hooks receive `PLUGIN_ROOT` and `PLUGIN_DATA`.
- Installing a plugin does not automatically trust its hooks.
- Matching handlers may run concurrently.
- `Bash`, `exec_command`, namespaced unified exec, `apply_patch`/`Edit`/`Write`,
  MCP tools, and most local
  tools can emit pre/post events; hosted tools do not use the local path.
- `UserPromptSubmit` and `Stop` ignore matchers.
- The plugin never merges or replaces the user's global `hooks.json`.

## Provider disclosure

Index and orientation generation and storage are local. When trusted Codex
hooks run, their bounded rendered orientation is placed in Codex
`additionalContext`. That text is part of the model request and is sent to the
configured provider unless the selected model transport is local. Hook trust
and local storage do not by themselves keep inference traffic on-device.
