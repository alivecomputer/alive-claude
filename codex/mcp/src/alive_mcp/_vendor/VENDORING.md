# Vendoring policy

This directory holds a frozen slice of ALIVE plugin kernel utilities so the
`alive-mcp` stdio JSON-RPC server can use them without the CLI hazards of the
upstream scripts (`print()` corrupts JSON-RPC framing; `sys.exit()` kills the
whole server process).

## Source

Upstream repository: `alivecontext/alive` (`github.com/alivecontext/alive`).
All paths below are relative to `claude-code/plugins/alive/scripts/` in that
repository.

## Copy date

2026-04-16 (fn-10-60k.2, task T2 of the alive-mcp v0.1 epic). Refreshed
2026-05-05 (fn-19 v3.3 identity-bridge task .10) for the v3.3 plugin
release; see "Refresh history" below.

## Source commit hashes

Each source file is pinned at the commit that most recently touched it on the
`main` branch at vendor time:

Upstream is `alivecontext/alive-staging` (private) until the P2P +
alive-mcp work graduates back to `alivecontext/alive`. Pins below
reference commits on `alive-staging:main`.

| Source file          | Upstream commit                            |
|----------------------|--------------------------------------------|
| `walnut_paths.py`    | `b50756a80238d8bd417fe30fec93305a1fefd6cc` |
| `project.py`         | `f91553c1796726eb3eb40490bd2056f3c99f7459` |
| `tasks.py`           | `2e3d77e1bff47fa620e0dfb8273b033ab98cd520` |

`walnut_paths.py` originated on `alivecontext/alive` via PR #32
(2026-04-20), which was reverted the same day after whiteboard testing.
The P2P work relanded on `alivecontext/alive-staging:main` as commit
`500f74a` and the pin now tracks that squash. File content is
byte-identical to the original `525ab597` tree; the byte-identity smoke
test (`tests/test_vendor_smoke.py::DirectCopyIsByteIdentical`)
continues to pass against the staging upstream.

When P2P re-promotes to `alivecontext/alive`, this pin will be updated
to the new public squash commit.

## Direct copy

One file is vendored verbatim -- byte-for-byte identical to upstream --
because it was purpose-built as a library (docstring declares the public
API, zero `print()`, zero `sys.exit()`):

- `walnut_paths.py` -- bundle path resolution and discovery. Layout-agnostic
  across v1 (`_core/_capsules/`), v2 (`bundles/`), and v3 (flat) walnuts.
  Stdlib only.

"Byte-for-byte identical" means `diff` returns zero bytes against the
upstream source at the pinned commit. `tests/test_vendor_smoke.py` asserts
this on every run so drift surfaces immediately -- see
`DirectCopyIsByteIdentical`. All vendor notes for this file live in this
document; NOTHING is added to or removed from the file itself. When the
upstream path isn't available at test time (typical for a CI run where the
alive-mcp package ships without the ALIVE plugin tree alongside), the
byte-identity test is skipped rather than failed -- the `diff` must run in
environments where both files are accessible (contributor checkouts of the
monorepo, or the vendor-refresh workflow).

## Extract-to-pure

Two source CLIs had their pure logic lifted into new modules under
`_pure/`. The CLIs themselves are NOT vendored -- their `print()` /
`sys.exit()` surface is forbidden inside a stdio MCP server.

| Upstream                                      | Extracted into              |
|-----------------------------------------------|-----------------------------|
| `project.py::parse_log` (L23-L199)            | `_pure/project_pure.py`     |
| `project.py::scan_bundles` (L206-L254)        | `_pure/project_pure.py`     |
| `project.py::parse_manifest` (L257-L304)      | `_pure/project_pure.py`     |
| `project.py::read_unscoped_tasks` (L351-L361) | `_pure/project_pure.py`     |
| `project.py::find_world_root` (L368-L379)     | `_pure/project_pure.py`     |
| `project.py::read_squirrel_sessions` (L382-)  | `_pure/project_pure.py`     |
| `project.py::scan_nested_walnuts` (L498-L546) | `_pure/project_pure.py`     |
| `project.py::assemble` (L553-L722)            | `_pure/project_pure.py`     |
| `tasks.py::_all_task_files` (L72-L103)        | `_pure/tasks_pure.py`       |
| `tasks.py::_collect_all_tasks` (L149-L156)    | `_pure/tasks_pure.py`       |
| `tasks.py::cmd_summary` body (L424-L584)      | `_pure/tasks_pure.py::summary_from_walnut` |

### Divergences from upstream

Documented inline in the module headers; summary here:

1. `find_world_root` raises `WorldNotFoundError` instead of returning
   `None`. Callers that used to check for `None` now catch the exception;
   the internal callers (`read_squirrel_sessions`) catch it to preserve
   upstream "empty-on-miss" semantics.
2. `parse_log` raises `KernelFileError` on unreadable log. Missing log
   remains a non-error (returns empty projection).
3. Malformed YAML / JSON no longer calls `print(..., file=sys.stderr)`
   directly. Instead, it emits `MalformedYAMLWarning` via the standard
   `warnings` module so the MCP audit layer can capture it with a warning
   filter. Note that Python's default warning handler still prints
   warnings to stderr unless the caller installs a filter or redirects
   the `warnings` module's output -- the guarantee is "no direct stderr
   writes from the library", not "nothing ever reaches stderr". The MCP
   server layer will install a filter so every `MalformedYAMLWarning`
   routes to the audit log with no fallthrough to stderr.
4. `assemble` no longer shells out to `tasks.py` via subprocess. Callers
   compose task data with `tasks_pure.summary_from_walnut` and pass the
   dict in as an argument (or omit it for the direct-`tasks.json` fallback).
5. No `argparse`, no `main()`, no `__main__` block. These are libraries.

## Error taxonomy

Defined in `_pure/__init__.py`:

| Name                    | Base           | When raised                             |
|-------------------------|----------------|-----------------------------------------|
| `WorldNotFoundError`    | `Exception`    | No ancestor of a path contains `.alive/` |
| `KernelFileError`       | `Exception`    | `_kernel/*` file present on disk but unreadable (permission, encoding, post-`isfile` I/O). Missing files are NOT errors -- helpers return empty shapes instead. |
| `MalformedYAMLWarning`  | `Warning`      | Structured-text parse/read failure on a kernel file, bundle manifest, squirrel entry, or `tasks.json` (YAML and JSON sources both emit this) |

`MalformedYAMLWarning` is named after the original YAML manifest path it
first guarded, but the extracted helpers emit it for every structured-text
read failure they swallow -- JSON task files, JSON `now.json` projections,
and YAML squirrel entries included. Callers filtering on this warning
should expect both format families. The name is retained for API
stability; if a format-agnostic rename happens later, the old name will
stay as an alias.

Exception classes map 1-to-1 onto v0.1 error-taxonomy codes that T4 defines
(`ERR_NO_WORLD`, `ERR_KERNEL_FILE_MISSING` / `ERR_KERNEL_FILE_CORRUPT`,
`ERR_MANIFEST_MALFORMED`).

## Refresh policy

Manual. On every upstream change to any of the three source files:

1. Check `git log -1 --format=%H -- claude-code/plugins/alive/scripts/{file}`
   in the upstream checkout.
2. If the hash differs from the table above:
   - **Direct-copy files** (`walnut_paths.py`): replace verbatim, update
     the commit hash in this file.
   - **Extracted files** (`project_pure.py`, `tasks_pure.py`): diff the
     upstream function against the extracted copy, port semantic changes,
     update the commit hash in this file.
3. Run `python3 -m unittest discover tests` from the `alive-mcp/` root to
   confirm the smoke suite still passes.
4. Commit with message `chore(vendor): refresh {walnut_paths|project|tasks}
   to upstream {short-hash}`.

No automated sync. Upstream churn in these files is low-frequency; the cost
of drift is lower than the cost of an auto-sync bot pulling a breaking
change into the MCP server on its own.

## Refresh history

### 2026-05-05 — plugin v3.3 (fn-19 task .10)

`walnut_paths.py` direct-copy refreshed from upstream commit
`b50756a80238d8bd417fe30fec93305a1fefd6cc` (fn-19 task .7
"feat(walnut_paths): ID-aware lookup + generate-index ids map"). Brings
in the v3.3 strangler-fig overlay: `WalnutHandle`, `WalnutResolutionError`,
`resolve_walnut`. Stdlib only (adds `from dataclasses import dataclass`,
re-uses existing `os`, `re`, `json`); zero `print()` / `sys.exit()`.
`tests/test_vendor_smoke.py::DirectCopyIsByteIdentical` passes.

`project_pure.py` and `tasks_pure.py` were INTENTIONALLY NOT refreshed
in this sweep. Rationale:

- alive-mcp v0.1 is read-only. The v3.3 upstream changes to
  `project.py` / `tasks.py` are write-side or `_common.py` refactors
  (auto-promote stash tasks, source_ref propagation through promote
  pipeline, `tasks.add_unlocked` lock-split, `_common.flock_file`
  helper). None of these touch the read-side functions extracted into
  `_pure/`.
- The "remove next primitive" change in upstream `cc99ef2` does drop
  the `next` field from `now.json` projections, but that is a v3.x
  product decision the MCP intentionally lags on: the MCP frontmatter
  schema and tool roster are frozen at v0.1; threading v3.x semantics
  into vendored read code would shift MCP behaviour out from under
  v0.1 consumers without a tool-roster bump.
- The T6 log-comment-strip in upstream `c880a79` does affect read-side
  `parse_log` behaviour (entry-hash markers leak into projections
  without it). DEFERRED to a follow-up vendor refresh after the MCP
  promotes off v0.1; logs at v3.3 don't yet ship hash markers in the
  prose body, so the leak is theoretical until older worlds with
  T6-shaped logs hit a v0.1 MCP. Tracked under epic fn-19 if the
  MCP needs the patch sooner.
- Per the project context, alive-mcp is post-v4.0 (atom rewrite); the
  v3.3 vendored extracts will be retired alongside `project.py` /
  `tasks.py` themselves once atoms land. Investing in another
  extract-to-pure port for a v3.x interim is wasted effort.

The `project.py` / `tasks.py` pin commits in the table above are
intentionally kept at the v0.1 vendor-time hashes to make the divergence
explicit. Refresh them only when (a) the MCP promotes to v0.2+ with a
broader read-surface, OR (b) a real bug surfaces in the extracted
read-side code traceable to upstream drift.

## Zero-side-effect import contract

Every module in `_vendor/` (including `_pure/`) MUST be import-safe: no
`print()`, no `sys.exit()`, no `warnings.warn` at import time, no filesystem
writes, no network. `tests/test_vendor_smoke.py` verifies this by importing
each module in a subprocess with stdout captured and asserting the capture
is empty.
