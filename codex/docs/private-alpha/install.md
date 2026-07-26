# ALIVE v3.3 Private-Alpha Install

## Requirements

- macOS for the tested alpha path.
- Codex CLI. The tested build is `0.146.0-alpha.3.1`.
- Python 3.10–3.13; Python 3.12 is the tested version.
- `uv` for locked MCP environment installation.
- An absolute path to the extracted `alive-codex-private-alpha` marketplace.

The runtime install uses `uv sync --frozen --no-install-project`: dependencies
come from the committed lock, while ALIVE itself runs directly from the
packaged `mcp/src` tree. This avoids editable-install path files and keeps the
installed cache relocatable.

Extract the `.tar.gz` before installation, preferably to a local non-cloud
temporary or Downloads directory. Do not point Codex directly at the generated
marketplace directory inside a cloud-synced workspace: on the tested macOS
build its cache copy stalled, while the clean archive extraction installed in
under one second.

## Install a built marketplace

```bash
MARKETPLACE=/absolute/path/alive-codex-private-alpha
PLUGIN="$MARKETPLACE/plugins/alive"

bash "$PLUGIN/install.sh" \
  --codex-home "${CODEX_HOME:-$HOME/.codex}" \
  --marketplace "$MARKETPLACE" \
  --uv-bin "$(command -v uv)"
```

On macOS the installer prefers the Codex binary bundled with ChatGPT/Codex
Desktop, then falls back to `command -v codex`. Pass `--codex-bin` only to
select a known working binary. The installer rejects launchers whose vendor
binary is missing instead of failing midway through installation.

The installer uses only `codex plugin marketplace add` and
`codex plugin add`. It does not edit global hooks or append feature flags.
It refuses installation when another `alive@...` product is enabled in the
same Codex profile. Disable the other ALIVE plugin and open a new task first;
v3.3 and v4 are not a supported combined runtime.

Then run:

```bash
bash "$PLUGIN/doctor.sh" \
  --codex-home "${CODEX_HOME:-$HOME/.codex}" \
  --json
```

Without a world path, doctor intentionally reports a warning because it cannot
verify an index/orientation pair. For a complete world check, prefer:

```bash
bash "$PLUGIN/doctor.sh" \
  --codex-home "${CODEX_HOME:-$HOME/.codex}" \
  --world "/absolute/path/to/MyWorld" \
  --json
```

With a valid current world cache and prepared MCP environment, the expected
top-level result is `"status": "pass"`. The world check uses the installed
strict validator and verifies the YAML/JSON generation pair plus the bounded
orientation's full source-index identity.

Open Codex and use `/hooks` to inspect and trust the installed ALIVE hooks.
For normal use, do not bypass hook trust.

## Build the marketplace from the v3 repository

From `codex/`:

```bash
python3 scripts/sync_shared_runtime.py \
  --source-root ../plugins/alive \
  --plugin-root . \
  --manifest shared-runtime.json \
  --check

python3 scripts/build_marketplace.py \
  --plugin-root . \
  --output dist/alive-codex-private-alpha
```

`--check` must return `{"divergent": []}`. The builder rejects caches,
virtual environments, tests, internal audit documents, conflicted duplicate
files, `node_modules`, and empty cloud placeholders. The optional MCP Inspector
contract dependency is installed only for development verification and is not
part of the artifact. Two builds must produce the same
`BUILD-MANIFEST.json`.

## Upgrade

```bash
bash "$PLUGIN/upgrade.sh" \
  --codex-bin "$(command -v codex)" \
  --codex-home "${CODEX_HOME:-$HOME/.codex}" \
  --marketplace "$MARKETPLACE" \
  --uv-bin "$(command -v uv)"
```

Review hook trust again if definitions changed.

## Uninstall

```bash
bash "$PLUGIN/uninstall.sh" \
  --codex-bin "$(command -v codex)" \
  --codex-home "${CODEX_HOME:-$HOME/.codex}" \
  --marketplace "$MARKETPLACE" \
  --remove-marketplace
```

Uninstall removes the plugin integration and cache through Codex. It does not
delete an ALIVE world. Keep your world backups independent of plugin lifecycle.

## Automation-only hook trust bypass

The E2E harness uses `--dangerously-bypass-hook-trust` only after validating
the exact built artifact. This is not an end-user install instruction and is
not required for normal use.

## Model-backed E2E harness

`scripts/e2e_codex_sessions.sh` ships inside the plugin, runs two distinct
ephemeral Codex processes, and writes JSON evidence. Synthetic mode is safe for
routine release verification:

```bash
bash scripts/e2e_codex_sessions.sh \
  --codex-bin /absolute/path/to/codex \
  --codex-home /absolute/path/to/isolated-codex-home \
  --plugin-root /absolute/path/to/installed/plugin \
  --source-world /absolute/path/to/synthetic/World \
  --source-walnut /absolute/path/to/synthetic/World/04_Ventures/demo \
  --run-root /absolute/new/path/e2e-run \
  --evidence /absolute/path/evidence.json \
  --classification synthetic \
  --token release-candidate-1
```

Private mode defaults to a minimum-disclosure export. It copies only the
selected walnut's `_kernel/key.md`, `_kernel/now.json`, and
`_kernel/insights.md`; it generates a neutral world identity plus empty test
log/tasks, and excludes historical sessions, old logs/tasks, inbox files,
indexes, squirrel records, manifests, and unrelated walnuts.

Run `--prepare-only` first. It performs no model call and returns `status:
prepared`, a source digest, and `disclosure-manifest.json` containing every
candidate file's path, origin, byte count, and SHA-256. A real private run exits
`77` before sending anything unless it also receives the exact acknowledgement
`--authorize-private-export I_AUTHORIZE_PRIVATE_WALNUT_EXPORT`. Authorization
does not override organization, tenant, sandbox, or provider data policy.

### Fully local private test

When Codex and an installed local provider support the required tool use and
structured output, private mode can stay on-device. Add:

```bash
--local-provider ollama --model gpt-oss:20b
```

The runner then invokes Codex with `--oss --local-provider ollama`, does not
require the private-export acknowledgement, and records `model_transport:
local:ollama` plus `private_context_sent: false`. Local-private mode uses the
full isolated world copy (`export_profile: whole-world-local`) so it can prove
real-world behavior without weakening the test; remote-private mode remains
minimum-disclosure. The local model remains a separate tested compatibility
target and does not create remote-provider privacy or lifecycle claims.
