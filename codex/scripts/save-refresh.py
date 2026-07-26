#!/usr/bin/env python3
"""Finish an explicit ALIVE save by refreshing its derived world state."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


SCRIPT_ROOT = Path(__file__).resolve().parent


def run(command: list[str]) -> None:
    completed = subprocess.run(command, text=True, capture_output=True)
    if completed.returncode == 0:
        return
    detail = completed.stderr.strip() or completed.stdout.strip() or "command failed"
    raise RuntimeError(f"{' '.join(command)}: {detail}")


def verify_orientation(world: Path) -> None:
    try:
        run(
            [
                sys.executable,
                str(SCRIPT_ROOT / "orientation.py"),
                "validate",
                str(world),
                "--identity-mode",
                "digest",
            ]
        )
        run(
            [
                sys.executable,
                str(SCRIPT_ROOT / "orientation.py"),
                "render",
                str(world),
                "--limit",
                "3",
            ]
        )
    except RuntimeError as error:
        raise RuntimeError(
            f"orientation cache failed strict schema or index identity validation: {error}"
        ) from error


def refresh(world: Path, walnut: Path | None) -> None:
    if walnut is not None:
        run([sys.executable, str(SCRIPT_ROOT / "project.py"), "--walnut", str(walnut)])
    run([sys.executable, str(SCRIPT_ROOT / "generate-index.py"), str(world)])
    run([sys.executable, str(SCRIPT_ROOT / "orientation.py"), "build", str(world)])
    verify_orientation(world)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--walnut", type=Path)
    args = parser.parse_args()
    world = args.world.resolve()
    if not world.joinpath(".alive").is_dir():
        parser.error(f"not an ALIVE world: {world}")
    if args.walnut is not None and not args.walnut.is_dir():
        parser.error(f"not a walnut directory: {args.walnut}")
    try:
        refresh(world, args.walnut)
    except (OSError, RuntimeError) as error:
        print(
            "Save checkpoint persistence may be recorded, but projection refresh is incomplete: "
            f"{error}",
            file=sys.stderr,
        )
        return 1
    mode = "active walnut" if args.walnut is not None else "standalone"
    print(f"ALIVE {mode} projection refresh complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
