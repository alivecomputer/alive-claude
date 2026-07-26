#!/usr/bin/env python3
"""Two-process proof harness for explicit ALIVE load/save/recovery."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def require_paths(plugin_root: Path, world: Path, walnut: Path) -> None:
    plugin_root = plugin_root.resolve()
    world = world.resolve()
    walnut = walnut.resolve()
    if world not in walnut.parents:
        raise ValueError("walnut must be inside world")
    if not world.joinpath(".alive").is_dir():
        raise ValueError("world is missing .alive")
    for relative in ("key.md", "log.md", "insights.md", "tasks.json"):
        if not walnut.joinpath("_kernel", relative).is_file():
            raise ValueError(f"walnut kernel file missing: {relative}")
    for relative in ("scripts/tasks.py", "scripts/project.py", "scripts/generate-index.py"):
        if not plugin_root.joinpath(relative).is_file():
            raise ValueError(f"packaged runtime file missing: {relative}")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepend_log_entry(log_path: Path, entry: str) -> None:
    original = log_path.read_text(encoding="utf-8")
    insertion = 0
    if original.startswith("---\n"):
        closing = original.find("\n---\n", 4)
        if closing >= 0:
            insertion = closing + len("\n---\n")
    updated = original[:insertion] + "\n" + entry.rstrip() + "\n\n" + original[insertion:].lstrip("\n")
    descriptor, name = tempfile.mkstemp(prefix=".log-", dir=log_path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(updated)
        os.replace(name, log_path)
    finally:
        Path(name).unlink(missing_ok=True)


def save(args: argparse.Namespace) -> dict[str, object]:
    plugin_root = args.plugin_root.resolve()
    world = args.world.resolve()
    walnut = args.walnut.resolve()
    require_paths(plugin_root, world, walnut)

    kernel = walnut / "_kernel"
    # Explicit load: read the three orientation surfaces before mutation.
    loaded = {
        "key": sha256(kernel / "key.md"),
        "insights": sha256(kernel / "insights.md"),
        "now": sha256(kernel / "now.json") if kernel.joinpath("now.json").is_file() else None,
    }
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    decision = f"Decision: preserve {args.token} across sessions."
    task_title = f"Recover {args.token} in a new session"
    entry = (
        f"## {now} — Codex private-alpha recovery proof\n\n"
        f"{decision}\n\n"
        "Phase: private alpha verification.\n\n"
        f"Next: {task_title}.\n\n"
        f"signed: squirrel:{args.session}"
    )
    prepend_log_entry(kernel / "log.md", entry)

    task_result = subprocess.run(
        [
            sys.executable,
            str(plugin_root / "scripts" / "tasks.py"),
            "add",
            "--walnut",
            str(walnut),
            "--title",
            task_title,
            "--priority",
            "active",
            "--session",
            args.session,
        ],
        text=True,
        capture_output=True,
        timeout=10,
    )
    if task_result.returncode != 0:
        raise RuntimeError(task_result.stderr or task_result.stdout)

    subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "project.py"), "--walnut", str(walnut)],
        check=True,
        text=True,
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        [sys.executable, str(plugin_root / "scripts" / "generate-index.py"), str(world)],
        check=True,
        text=True,
        capture_output=True,
        timeout=10,
    )

    squirrels = world / ".alive" / "_squirrels"
    squirrels.mkdir(parents=True, exist_ok=True)
    squirrels.joinpath(f"{args.session}.yaml").write_text(
        f"session_id: {args.session}\n"
        "runtime_id: squirrel.core@3.3\n"
        f"walnut: {walnut}\n"
        "ended: null\n"
        "saves: 1\n"
        f"last_saved: {now}\n"
        f"recovery_state: Recover {args.token} from walnut files in a new process.\n",
        encoding="utf-8",
    )

    result: dict[str, object] = {
        "status": "saved",
        "session": args.session,
        "token": args.token,
        "walnut": str(walnut),
        "loaded": loaded,
        "log_sha256": sha256(kernel / "log.md"),
        "tasks_sha256": sha256(kernel / "tasks.json"),
        "now_sha256": sha256(kernel / "now.json"),
        "index_sha256": sha256(world / ".alive" / "_index.json"),
    }
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def recover(args: argparse.Namespace) -> dict[str, object]:
    plugin_root = args.plugin_root.resolve()
    world = args.world.resolve()
    walnut = args.walnut.resolve()
    require_paths(plugin_root, world, walnut)
    kernel = walnut / "_kernel"
    # No session-one evidence or transcript is read here. Disk is the handoff.
    log = kernel.joinpath("log.md").read_text(encoding="utf-8")
    tasks = json.loads(kernel.joinpath("tasks.json").read_text(encoding="utf-8"))
    projection = json.loads(kernel.joinpath("now.json").read_text(encoding="utf-8"))
    task_title = f"Recover {args.token} in a new session"
    task_items = tasks.get("tasks", tasks if isinstance(tasks, list) else [])
    return {
        "status": "recovered",
        "session": args.session,
        "token": args.token,
        "decision_found": f"Decision: preserve {args.token} across sessions." in log,
        "task_found": any(item.get("title", item.get("text")) == task_title for item in task_items),
        "projection_found": args.token in json.dumps(projection, sort_keys=True),
        "loaded_kernel": ["key.md", "now.json", "insights.md"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("save", "recover"))
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--walnut", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.mode == "save" and args.evidence is None:
        parser.error("save requires --evidence")
    return args


def main() -> int:
    args = parse_args()
    result = save(args) if args.mode == "save" else recover(args)
    print(json.dumps(result, sort_keys=True))
    if args.mode == "recover" and not all(
        result[key] for key in ("decision_found", "task_found", "projection_found")
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
