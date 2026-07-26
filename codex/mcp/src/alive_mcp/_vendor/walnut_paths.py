#!/usr/bin/env python3
"""ALIVE Context System -- walnut path helpers (vendored).

Public API for resolving and discovering bundles inside a walnut. Vendors the
v3-aware bundle resolution and scanning logic from
``plugins/alive/scripts/tasks.py`` (``_resolve_bundle_path`` / ``_find_bundles``)
and ``plugins/alive/scripts/project.py`` (``scan_bundles``) under stable public
names so external callers do not import underscored privates that may change
without notice across plugin updates.

This module exists per LD10 of the fn-7-7cw epic spec. ``alive-p2p.py`` (and any
future v3 P2P consumer) imports from here instead of from tasks.py / project.py
directly. The vendored implementations remain layout-agnostic: they handle v3
flat bundles at walnut root, v2 ``bundles/`` containers, and v1
``_core/_capsules/`` legacy capsules.

v3.3 identity-bridge surface (T7): :class:`WalnutHandle`,
:class:`WalnutResolutionError`, and :func:`resolve_walnut` add ID-aware lookup
that coexists with the path-based API as new surface only. Existing callers
(``resolve_bundle_path`` at line 46, ``tasks.py`` bundle resolution,
``alive-p2p.py`` path-fallback) are NOT migrated under v3.3 — caller migration
is explicitly deferred to v3.3.1+ per epic strangler-fig discipline.

Stdlib only. No PyYAML. Type hints use the ``typing`` module (3.9 floor).
"""

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# Directories that are skipped during bundle discovery. Mirrors the union of
# project.py::scan_bundles and tasks.py::_find_bundles skip lists, plus the
# obvious archive / build paths a v3 walnut may carry.
_SKIP_DIRS = {
    "_kernel",
    "_core",
    ".git",
    ".alive",
    "node_modules",
    "raw",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "target",
    "_archive",
    "_references",
    "01_Archive",
}


def resolve_bundle_path(walnut, bundle):
    # type: (str, str) -> Optional[str]
    """Find a bundle directory by name. Returns absolute path or None.

    Layout fallback order:
        1. v3 flat:    ``{walnut}/{bundle}``
        2. v2 nested:  ``{walnut}/bundles/{bundle}``
        3. v1 legacy:  ``{walnut}/_core/_capsules/{bundle}``

    Returns None when none of the candidates exist on disk. Unlike the
    ``tasks.py`` private which returns a v3 placeholder for new-bundle creation,
    this function refuses to invent paths -- callers can decide how to handle
    "not found" themselves.
    """
    if not bundle:
        return None

    candidates = (
        os.path.join(walnut, bundle),
        os.path.join(walnut, "bundles", bundle),
        os.path.join(walnut, "_core", "_capsules", bundle),
    )
    for candidate in candidates:
        if os.path.isdir(candidate):
            return os.path.abspath(candidate)
    return None


def find_bundles(walnut):
    # type: (str) -> List[Tuple[str, str]]
    """Walk a walnut and return ``(bundle_relpath, abs_path)`` tuples.

    Discovery rules:
        - A directory is a bundle if it contains ``context.manifest.yaml``
          (v2/v3) or ``companion.md`` (v1 legacy).
        - ``bundle_relpath`` is POSIX-normalized (forward slashes), relative to
          ``walnut``. Top-level bundles report their bare directory name; nested
          bundles report e.g. ``archive/old/bundle-a``.
        - Hidden directories and entries in ``_SKIP_DIRS`` are pruned.
        - Nested walnut roots (any directory containing ``_kernel/key.md``) are
          treated as boundaries: their interior is NEVER scanned, so a parent's
          ``find_bundles`` does not bleed into a child walnut's bundles.

    Results are sorted by ``bundle_relpath`` for stable test fixtures.
    """
    walnut = os.path.abspath(walnut)
    bundles = []  # type: List[Tuple[str, str]]
    nested_walnut_roots = set()  # type: set

    for root, dirs, files in os.walk(walnut):
        rel = os.path.relpath(root, walnut)

        # Prune hidden + skip dirs in-place so os.walk does not descend into
        # them. The ``_SKIP_DIRS`` set is intentionally tight: anything outside
        # it is candidate ground for bundle discovery.
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in _SKIP_DIRS
        ]

        # If the current directory sits inside a nested walnut we already
        # detected, skip it entirely.
        if rel != ".":
            inside_nested = False
            for nested in nested_walnut_roots:
                if rel == nested or rel.startswith(nested + os.sep):
                    inside_nested = True
                    break
            if inside_nested:
                dirs[:] = []
                continue

        # Detect a nested walnut boundary: a non-root directory that contains
        # ``_kernel/key.md``. Mark the relpath as a boundary and stop descending.
        if rel != ".":
            kernel_key = os.path.join(root, "_kernel", "key.md")
            if os.path.isfile(kernel_key):
                nested_walnut_roots.add(rel)
                dirs[:] = []
                continue

        # Bundle detection. v2/v3 takes precedence; v1 only fires if a manifest
        # is absent (matches the ``elif`` order in tasks.py::_find_bundles).
        is_bundle = False
        if "context.manifest.yaml" in files:
            is_bundle = True
        elif "companion.md" in files:
            is_bundle = True

        if is_bundle:
            if rel == ".":
                # The walnut root itself is not a bundle even if a stray
                # manifest sits there. Skip it.
                continue
            relpath_posix = rel.replace(os.sep, "/")
            bundles.append((relpath_posix, os.path.abspath(root)))

    bundles.sort(key=lambda b: b[0])
    return bundles


def scan_bundles(walnut):
    # type: (str) -> Dict[str, Dict[str, Any]]
    """Return ``{bundle_relpath: parsed_manifest_dict}`` for every discoverable bundle.

    Uses ``find_bundles`` for discovery and a regex-only manifest parser for
    field extraction. Bundles whose manifest cannot be read or parsed are
    omitted from the result -- callers should treat absence as "no usable
    metadata", not "no bundle".

    The parsed manifest dict is intentionally minimal: it carries the same
    fields ``project.py::parse_manifest`` extracts (goal, status, updated, due,
    context, active_sessions). Future fields can be added without changing the
    public signature.
    """
    result = {}  # type: Dict[str, Dict[str, Any]]
    for relpath, abs_path in find_bundles(walnut):
        manifest_path = os.path.join(abs_path, "context.manifest.yaml")
        parsed = _parse_manifest_minimal(manifest_path)
        if parsed is not None:
            result[relpath] = parsed
    return result


def _parse_manifest_minimal(filepath):
    # type: (str) -> Optional[Dict[str, Any]]
    """Regex-only parse of ``context.manifest.yaml``. Returns dict or None.

    Mirrors the contract of ``project.py::parse_manifest``: stdlib only, no
    PyYAML, tolerates missing fields, returns None only on read error so the
    caller can distinguish "manifest unreadable" from "manifest empty".
    """
    if not os.path.isfile(filepath):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError, UnicodeDecodeError):
        return None

    result = {}  # type: Dict[str, Any]

    # Simple single-line scalar fields. The list mirrors project.py and adds a
    # few that bundle manifests commonly carry.
    for field in ("goal", "status", "updated", "due", "name", "outcome", "phase"):
        pattern = r"^{0}:\s*['\"]?(.*?)['\"]?\s*$".format(re.escape(field))
        m = re.search(pattern, content, re.MULTILINE)
        if m:
            result[field] = m.group(1).strip()

    # Multi-line context block (``context: |`` or ``context: >``). Falls back
    # to a single-line capture if the block form is absent.
    ctx_block = re.search(
        r"^context:\s*[|>]-?\s*\n((?:[ \t]+.+\n?)*)",
        content,
        re.MULTILINE,
    )
    if ctx_block:
        lines = ctx_block.group(1).split("\n")
        stripped = [ln.strip() for ln in lines if ln.strip()]
        result["context"] = "\n".join(stripped)
    else:
        ctx_simple = re.search(
            r"^context:\s*['\"]?(.*?)['\"]?\s*$",
            content,
            re.MULTILINE,
        )
        if ctx_simple:
            result["context"] = ctx_simple.group(1).strip()

    # active_sessions list (used by P2P stripping logic and project.py).
    sessions = []  # type: List[str]
    sq_match = re.search(
        r"^squirrels:\s*\n((?:[ \t]*-\s*.+\n?)*)",
        content,
        re.MULTILINE,
    )
    if sq_match:
        for item in re.finditer(r"-\s*(\S+)", sq_match.group(1)):
            sessions.append(item.group(1))
    result["active_sessions"] = sessions

    return result


# ---------------------------------------------------------------------------
# v3.3 identity-bridge: ID-aware lookup (T7)
# ---------------------------------------------------------------------------
#
# Strangler-fig overlay on top of the path-based resolver above. Adds a
# ``WalnutHandle`` typed return + a ``resolve_walnut`` function that accepts
# either a canonical ``wal_<ULID>`` id or a filesystem path. Path-based
# resolution remains untouched; existing callers do not migrate under v3.3.
#
# World resolution is explicit (locked decision #10):
#     1. caller-supplied ``world_root`` arg, else
#     2. ``find_world_root(cwd)``, else
#     3. raise ``WalnutResolutionError(code="NO_WORLD")``.
# That error case maps the "ID lookup outside a walnut" + "ambiguous
# multi-world cwd" failure modes to a single explicit failure rather than a
# silent miss.

#: Canonical walnut id shape -- lowercase Crockford-base32 (mirrors the
#: locked emit invariant from T1 / migrate_canonical_ids). Re-compiled here
#: so this module does not pull ``_common`` for a constant.
_WALNUT_ID_RE = re.compile(r"^wal_[0-9a-hjkmnp-tv-z]{26}$")


class WalnutResolutionError(Exception):
    """Raised when :func:`resolve_walnut` cannot satisfy a lookup.

    Attributes
    ----------
    code : str
        Stable machine-readable failure tag. One of:

        * ``NO_WORLD`` -- no world_root arg given AND ``find_world_root(cwd)``
          fails. Hint: pass ``world_root=`` explicitly or run from inside a
          walnut tree.
        * ``ID_NOT_FOUND`` -- input matches the canonical walnut-id shape but
          the resolved world's ``_index.json`` ``ids`` map has no entry for
          it. Hint: re-run ``alive generate-index`` /
          ``alive migrate-canonical-ids``.
        * ``WALNUT_OUTSIDE_WORLD`` -- input is a path that resolves outside
          the supplied (or discovered) ``world_root``.
        * ``NOT_A_WALNUT`` -- input is a path but does not contain
          ``_kernel/key.md``. Defensive guard so callers get a typed error
          rather than a stale ``WalnutHandle`` over a bare directory.

    hint : str
        Human-readable next-step. Always populated; agents surface it back
        to the operator.
    """

    def __init__(self, code, hint):
        # type: (str, str) -> None
        self.code = code
        self.hint = hint
        super().__init__("{}: {}".format(code, hint))


@dataclass
class WalnutHandle:
    """Typed return for :func:`resolve_walnut`.

    Attributes
    ----------
    path : str
        Absolute path to the walnut directory (``_kernel/key.md`` lives at
        ``{path}/_kernel/key.md``).
    walnut_id : str | None
        Canonical ``wal_<ULID>`` id when known. ``None`` for unmigrated
        walnuts that were resolved by path. Callers that need a guaranteed
        id must handle the ``None`` case (or run migration first).
    name : str
        Basename of ``path`` -- the folder name of the walnut. Stable for
        agents that key on it for display.
    """

    path: str
    walnut_id: Optional[str]
    name: str


# Process-local cache: ``world_root -> {walnut_id: walnut_path}``. Keyed on
# the realpath-normalized world root so a caller passing in the same world
# via two surface forms (symlink vs canonical) does not pay the JSON read
# twice. Cleared on process exit. Tests that mutate ``_index.json`` between
# resolve calls within the same process must invalidate by calling
# :func:`_clear_resolve_walnut_cache` (defined below) -- otherwise they
# observe the first read.
_RESOLVE_WALNUT_IDS_CACHE = {}  # type: Dict[str, Dict[str, str]]


def _clear_resolve_walnut_cache():
    # type: () -> None
    """Drop the in-process ``ids`` map cache.

    Test-only seam. Production callers do not need this; the cache lifetime
    is the process lifetime, and ``alive`` subcommands re-exec per
    invocation. Tests that rebuild ``_index.json`` mid-test call this to
    force a re-read.
    """
    _RESOLVE_WALNUT_IDS_CACHE.clear()


def _load_world_ids_map(world_root):
    # type: (str) -> Dict[str, str]
    """Load ``{walnut_id: walnut_abs_path}`` from a world's ``_index.json``.

    Returns an empty dict when the index is absent, unreadable, malformed,
    or carries no ``ids`` field (i.e. was generated by a pre-v3.3
    ``generate-index.py``). The empty-dict path is what triggers
    ``ID_NOT_FOUND`` in :func:`resolve_walnut` -- a missing index is treated
    the same as an index that simply has no entry for the requested id, so
    operators get the same hint either way (re-run migration / index).

    Resolves walnut paths relative to ``world_root`` so the cache can be
    shared by callers that pass the same world via different surface forms.
    """
    cache_key = os.path.realpath(world_root)
    if cache_key in _RESOLVE_WALNUT_IDS_CACHE:
        return _RESOLVE_WALNUT_IDS_CACHE[cache_key]
    index_path = os.path.join(world_root, ".alive", "_index.json")
    out = {}  # type: Dict[str, str]
    if os.path.isfile(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (IOError, OSError, json.JSONDecodeError):
            data = None
        if isinstance(data, dict):
            ids = data.get("ids")
            if isinstance(ids, dict):
                walnut_ids = ids.get("walnuts")
                if isinstance(walnut_ids, dict):
                    for wal_id, rel_or_abs in walnut_ids.items():
                        if not isinstance(wal_id, str) or not isinstance(rel_or_abs, str):
                            continue
                        if os.path.isabs(rel_or_abs):
                            out[wal_id] = rel_or_abs
                        else:
                            out[wal_id] = os.path.abspath(
                                os.path.join(world_root, rel_or_abs)
                            )
    _RESOLVE_WALNUT_IDS_CACHE[cache_key] = out
    return out


def _read_walnut_id_from_kernel(walnut_path):
    # type: (str) -> Optional[str]
    """Read the canonical ``walnut_id`` from a walnut's ``_kernel/key.md``.

    Returns ``None`` if the file is missing, has no frontmatter, or has no
    canonical-shaped ``walnut_id``. Used by the path-resolution branch so
    the returned :class:`WalnutHandle` carries an id when one exists on
    disk -- callers that resolved by path on a migrated walnut still get
    the canonical id back.

    Stdlib-only regex parser; mirrors the lowercase-Crockford emit shape.
    Does NOT validate via the full ULID round-trip -- a present-but-
    malformed value is surfaced by ``alive doctor --check=canonical-ids``,
    not silently rewritten or re-emitted here.
    """
    key_md = os.path.join(walnut_path, "_kernel", "key.md")
    if not os.path.isfile(key_md):
        return None
    try:
        with open(key_md, "r", encoding="utf-8") as f:
            content = f.read()
    except (IOError, OSError, UnicodeDecodeError):
        return None
    fm = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm:
        return None
    body = fm.group(1)
    for line in body.splitlines():
        if line[:1] in (" ", "\t"):
            continue
        m = re.match(r"^walnut_id\s*:\s*(.*)$", line)
        if not m:
            continue
        raw = m.group(1).strip()
        if (raw.startswith('"') and raw.endswith('"')) or (
            raw.startswith("'") and raw.endswith("'")
        ):
            raw = raw[1:-1]
        if _WALNUT_ID_RE.match(raw):
            return raw
        return None
    return None


def _resolve_world_root(world_root):
    # type: (Optional[str]) -> str
    """Resolve world_root: explicit arg > find_world_root(cwd) > raise.

    Locked decision #10: explicit > discovered > error. The discovered case
    falls through to ``WalnutResolutionError(code="NO_WORLD")`` so callers
    that resolve "from outside any walnut tree" get a typed failure rather
    than a silent miss.
    """
    if world_root is not None:
        return os.path.abspath(os.path.expanduser(os.fspath(world_root)))
    # Local import so the module's normal import surface stays cheap.
    try:
        from _common import find_world_root  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - defensive
        raise WalnutResolutionError(
            code="NO_WORLD",
            hint=(
                "could not import _common.find_world_root; pass world_root "
                "explicitly. Underlying error: {}".format(exc)
            ),
        )
    try:
        return find_world_root(os.getcwd())
    except FileNotFoundError as exc:
        raise WalnutResolutionError(
            code="NO_WORLD",
            hint=(
                "pass world_root or run from inside a walnut tree "
                "(underlying: {})".format(exc)
            ),
        )


def resolve_walnut(id_or_path, world_root=None):
    # type: (str, Optional[str]) -> WalnutHandle
    """Resolve a walnut by canonical id OR by filesystem path.

    Resolution order:

      1. Resolve ``world_root``: explicit arg, else ``find_world_root(cwd)``,
         else raise ``WalnutResolutionError(code="NO_WORLD")``.
      2. If ``id_or_path`` matches ``^wal_<26-char-lowercase-Crockford>$``,
         look it up via the resolved world's ``.alive/_index.json`` ``ids``
         map. Miss → ``WalnutResolutionError(code="ID_NOT_FOUND")`` with a
         hint to re-run migration / generate-index.
      3. Else treat as a filesystem path. The path must contain
         ``_kernel/key.md`` (defensive: ``NOT_A_WALNUT`` otherwise) AND must
         resolve inside the supplied / discovered ``world_root``
         (``WALNUT_OUTSIDE_WORLD`` otherwise -- catches the ``--world A``
         + ``walnut B`` mismatch case at the call site rather than later
         in a downstream operation).
      4. Returns a :class:`WalnutHandle`. ``walnut_id`` is populated when
         the walnut's ``_kernel/key.md`` carries a canonical id, ``None``
         for unmigrated walnuts.

    This is a v3.3 strangler-fig surface: existing path-based callers are
    NOT migrated. ``resolve_bundle_path`` and bundle-resolution helpers in
    ``tasks.py`` / ``alive-p2p.py`` keep their current behaviour.

    Args:
        id_or_path: Either a canonical ``wal_<ULID>`` string or a filesystem
            path to a walnut directory.
        world_root: Optional world root override. ``None`` triggers cwd
            walk-up via ``_common.find_world_root``.

    Returns:
        :class:`WalnutHandle`.

    Raises:
        WalnutResolutionError: with one of ``NO_WORLD``, ``ID_NOT_FOUND``,
            ``WALNUT_OUTSIDE_WORLD``, ``NOT_A_WALNUT``.
    """
    if not id_or_path:
        raise WalnutResolutionError(
            code="NOT_A_WALNUT",
            hint="empty id_or_path; pass a canonical wal_<ULID> or a path",
        )

    world = _resolve_world_root(world_root)
    world_real = os.path.realpath(world)
    world_with_sep = world_real.rstrip(os.sep) + os.sep

    # ---- ID branch -----------------------------------------------------
    if _WALNUT_ID_RE.match(id_or_path):
        ids_map = _load_world_ids_map(world)
        candidate = ids_map.get(id_or_path)
        if candidate is None:
            raise WalnutResolutionError(
                code="ID_NOT_FOUND",
                hint=(
                    "id {!r} not present in {}/.alive/_index.json; "
                    "run alive generate-index --world {} or "
                    "alive migrate-canonical-ids --world {}".format(
                        id_or_path, world, world, world
                    )
                ),
            )
        # Containment guard: a stale or hand-edited index could point at a
        # path that no longer lives under the supplied world. Treat that as
        # ``WALNUT_OUTSIDE_WORLD`` rather than silently returning a handle
        # that bridges worlds.
        candidate_real = os.path.realpath(candidate)
        if not (
            candidate_real == world_real
            or candidate_real.startswith(world_with_sep)
        ):
            raise WalnutResolutionError(
                code="WALNUT_OUTSIDE_WORLD",
                hint=(
                    "id {!r} resolves to {} which is outside world_root "
                    "{}".format(id_or_path, candidate_real, world_real)
                ),
            )
        if not os.path.isfile(os.path.join(candidate, "_kernel", "key.md")):
            raise WalnutResolutionError(
                code="NOT_A_WALNUT",
                hint=(
                    "id {!r} maps to {} but _kernel/key.md is missing; "
                    "the index may be stale -- re-run alive generate-index".format(
                        id_or_path, candidate
                    )
                ),
            )
        return WalnutHandle(
            path=os.path.abspath(candidate),
            walnut_id=id_or_path,
            name=os.path.basename(os.path.normpath(candidate)),
        )

    # ---- Path branch ---------------------------------------------------
    walnut_path = os.path.abspath(os.path.expanduser(id_or_path))
    if not os.path.isfile(os.path.join(walnut_path, "_kernel", "key.md")):
        raise WalnutResolutionError(
            code="NOT_A_WALNUT",
            hint=(
                "{!r} does not contain _kernel/key.md; pass a canonical "
                "wal_<ULID> id or the absolute path of a walnut directory".format(
                    walnut_path
                )
            ),
        )
    walnut_real = os.path.realpath(walnut_path)
    if not (
        walnut_real == world_real
        or walnut_real.startswith(world_with_sep)
    ):
        raise WalnutResolutionError(
            code="WALNUT_OUTSIDE_WORLD",
            hint=(
                "{} is outside world_root {} (resolved: {} vs {})".format(
                    walnut_path, world, walnut_real, world_real
                )
            ),
        )
    walnut_id = _read_walnut_id_from_kernel(walnut_path)
    return WalnutHandle(
        path=walnut_path,
        walnut_id=walnut_id,
        name=os.path.basename(os.path.normpath(walnut_path)),
    )


__all__ = [
    "resolve_bundle_path",
    "find_bundles",
    "scan_bundles",
    "WalnutHandle",
    "WalnutResolutionError",
    "resolve_walnut",
]
