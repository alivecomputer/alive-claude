#!/usr/bin/env python3
"""Copy the allowlisted ALIVE v3 runtime into the Codex adapter."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path


IGNORED_PARTS = {".DS_Store", ".pytest_cache", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_paths(source_root: Path, manifest_path: Path) -> list[Path]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    relatives: set[Path] = set()
    for value in payload.get("files", []):
        relatives.add(Path(value))
    for value in payload.get("trees", []):
        tree = source_root / value
        if not tree.is_dir():
            raise FileNotFoundError(f"shared runtime tree not found: {tree}")
        for candidate in tree.rglob("*"):
            if not candidate.is_file():
                continue
            if candidate.stat().st_size == 0:
                continue
            relative = candidate.relative_to(source_root)
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            if candidate.suffix in IGNORED_SUFFIXES:
                continue
            relatives.add(relative)
    return sorted(relatives, key=lambda value: value.as_posix())


def sync(
    source_root: Path, plugin_root: Path, manifest_path: Path, *, check: bool
) -> list[str]:
    divergent: list[str] = []
    for relative in load_paths(source_root, manifest_path):
        source = source_root / relative
        destination = plugin_root / relative
        if not source.is_file():
            raise FileNotFoundError(f"shared runtime file not found: {source}")
        if not destination.is_file() or digest(source) != digest(destination):
            divergent.append(relative.as_posix())
            if check:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", dir=destination.parent
            )
            os.close(descriptor)
            temporary = Path(temporary_name)
            try:
                shutil.copy2(source, temporary)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
    return divergent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    divergent = sync(
        args.source_root.resolve(),
        args.plugin_root.resolve(),
        args.manifest.resolve(),
        check=args.check,
    )
    print(json.dumps({"divergent": divergent}, sort_keys=True))
    return 1 if args.check and divergent else 0


if __name__ == "__main__":
    raise SystemExit(main())
