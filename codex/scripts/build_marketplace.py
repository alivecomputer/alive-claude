#!/usr/bin/env python3
"""Build a deterministic local Codex marketplace for the ALIVE plugin."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path


EXCLUDED_PARTS = {
    ".DS_Store",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "dist",
    "docs-internal",
    "node_modules",
    "tests",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def release_files(plugin_root: Path) -> list[Path]:
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(plugin_root):
        directory_path = Path(directory)
        relative_directory = directory_path.relative_to(plugin_root)
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in EXCLUDED_PARTS
            and not (
                relative_directory == Path("docs") and name == "superpowers"
            )
        )
        for name in sorted(filenames):
            if name in EXCLUDED_PARTS:
                continue
            path = directory_path / name
            if path.stat().st_size == 0:
                continue
            if path.suffix in EXCLUDED_SUFFIXES:
                continue
            files.append(path.relative_to(plugin_root))
    return sorted(files, key=lambda item: item.as_posix())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(plugin_root: Path, output: Path) -> Path:
    plugin_root = plugin_root.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        installed = temporary / "plugins" / "alive"
        for relative in release_files(plugin_root):
            destination = installed / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = plugin_root / relative
            # Avoid macOS fcopyfile(3): on provenance-tagged plugin sources it
            # can block indefinitely. A bounded userspace copy is deterministic
            # and copies content only, which is exactly what the artifact needs.
            with source.open("rb") as input_handle, destination.open("wb") as output_handle:
                shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
            destination.chmod(stat.S_IMODE(source.stat().st_mode))

        catalog_path = temporary / ".agents" / "plugins" / "marketplace.json"
        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog = {
            "name": "alive-private-alpha",
            "interface": {"displayName": "ALIVE Private Alpha"},
            "plugins": [
                {
                    "name": "alive",
                    "source": {"source": "local", "path": "./plugins/alive"},
                    "policy": {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    },
                    "category": "Productivity",
                }
            ],
        }
        catalog_path.write_text(
            json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        manifest_files: dict[str, str] = {}
        for path in sorted(temporary.rglob("*")):
            if path.is_file() and path.name != "BUILD-MANIFEST.json":
                manifest_files[path.relative_to(temporary).as_posix()] = sha256(path)
        temporary.joinpath("BUILD-MANIFEST.json").write_text(
            json.dumps(
                {
                    "format": 1,
                    "plugin": "alive",
                    "version": "3.3.0-alpha.3",
                    "files": manifest_files,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.plugin_root, args.output)
    print(json.dumps({"marketplace": str(result)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
