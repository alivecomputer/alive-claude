# ALIVE v3.3 for Codex

ALIVE v3.3 is a private-alpha Codex plugin for people who already use the
filesystem-first ALIVE v3 walnut format. It packages explicit load and save
skills, native Codex lifecycle hooks, the shared v3 projection runtime, and a
read-only MCP server.

Status: **private alpha**. Tested on macOS with
`codex-cli 0.146.0-alpha.3.1`. It is not yet submitted to the public Codex
plugin directory.

## What is proven

- The marketplace artifact installs into a fresh `CODEX_HOME` without using
  paths from the development checkout.
- Clean install, repeat install, upgrade, doctor, and uninstall preserve
  unrelated Codex configuration and user worlds.
- The same ALIVE v3 walnut format is used; no v4 or `exitplatforms` runtime is
  required.
- A completed explicit save can be recovered by a distinct process with no
  transcript handoff. This passed on both a fixture and an isolated copy of a
  real walnut.
- Two distinct model-backed Codex processes completed the same save/recovery
  proof on both generated synthetic data and an isolated copy of a real walnut
  using the freshly installed plugin. The private real-walnut run used local
  Ollama `gpt-oss:20b`; session two recovered the exact disk token, did not
  change the copied kernel, and the source world digest stayed unchanged.
- Twelve MCP tools are read-only, carry non-destructive annotations, make no
  outbound network calls, and pass the recovered MCP test suite.
- Native hook scripts pass schema and subprocess tests for startup, resume,
  clear, compaction, writes, and stop handling.
- The current Codex manifest validator accepts the package. Hook definitions
  use default `hooks/hooks.json` discovery rather than an unsupported
  `plugin.json` field.
- Repeated startup for the same session preserves the loaded walnut, save
  count, and recovery state instead of resetting them.

Only one ALIVE product may be enabled in a Codex profile. The installer and
doctor reject a simultaneous v3.3 private alpha plus the v4 `alivecontext`
plugin because those products expose contradictory skills and persistence
semantics.

## What is not promised

Hooks are optional, trust-gated, disableable, and concurrent. They are useful
lifecycle assistance, not a security boundary and not a guarantee that every
operation or abrupt exit is observed. Hosted tools do not always emit local
tool hooks. Explicit `alive-save` is the guaranteed persistence path.

Model access and two-session Codex mechanics are proven locally with a real
walnut copy and `gpt-oss:20b` through Ollama. No walnut content was sent to
OpenAI in that test. A remote-provider private run remains separately unproven:
this environment prohibited that disclosure even after approval, and nothing
was sent. Remote private preflight defaults to a minimum-disclosure export and
emits an exact hash/size manifest before any model call.

## Install

Use the built private marketplace and follow
[`docs/private-alpha/install.md`](docs/private-alpha/install.md). After
installation, open `/hooks` inside Codex, inspect the ALIVE definitions, and
trust them if they match the package you installed.

## Privacy

Walnuts remain local files. The packaged MCP server has no phone-home path.
Preparing MCP downloads locked Python dependencies. When you ask Codex to read
a walnut through a remote model, the selected context is sent to that provider
under your account and its applicable data controls. The tested Ollama path
runs the model locally and records `private_context_sent: false`; local
deployment security remains your responsibility.

When you review and trust the Codex lifecycle hooks, the bounded rendered
orientation they add through `additionalContext` is also part of the model
request. It is sent to the configured provider unless that model transport is
local. Local file generation and storage are not a promise of local-only
inference.

See the full
[`compatibility matrix`](docs/private-alpha/compatibility.md),
[`public-release gaps`](docs/private-alpha/public-release-gaps.md), and
[`v3.3 roadmap`](docs/v3.3/roadmap.md).
