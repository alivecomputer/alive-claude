#!/usr/bin/env python3
"""Model-backed, two-process Codex proof for an isolated ALIVE world copy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PRIVATE_AUTHORIZATION = "I_AUTHORIZE_PRIVATE_WALNUT_EXPORT"
PRIVATE_SOURCE_FILES = ("key.md", "now.json", "insights.md")


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def file_record(root: Path, path: Path, origin: str) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "origin": origin,
    }


def export_world(
    source_world: Path,
    source_walnut: Path,
    copied_world: Path,
    *,
    classification: str,
    local_provider: str | None,
    manifest_path: Path,
) -> tuple[Path, str, list[dict[str, Any]]]:
    walnut_relative = source_walnut.relative_to(source_world)
    origins: dict[str, str] = {}
    if classification == "synthetic" or local_provider:
        shutil.copytree(source_world, copied_world)
        profile = "whole-world-local" if local_provider else "whole-world"
        origins = {
            path.relative_to(copied_world).as_posix(): "source"
            for path in copied_world.rglob("*")
            if path.is_file()
        }
    else:
        profile = "minimum"
        for directory in ("01_Archive", "02_Life", "03_Inbox", "04_Ventures"):
            copied_world.joinpath(directory).mkdir(parents=True, exist_ok=True)
        alive_key = copied_world / ".alive" / "key.md"
        alive_key.parent.mkdir(parents=True, exist_ok=True)
        alive_key.write_text(
            "---\nname: ALIVE private E2E test\nclassification: private-test-copy\n---\n",
            encoding="utf-8",
        )
        origins[alive_key.relative_to(copied_world).as_posix()] = "generated"

        copied_kernel = copied_world / walnut_relative / "_kernel"
        copied_kernel.mkdir(parents=True, exist_ok=True)
        source_kernel = source_walnut / "_kernel"
        for name in PRIVATE_SOURCE_FILES:
            source = source_kernel / name
            if not source.is_file():
                continue
            if source.is_symlink():
                raise ValueError(f"private export refuses symlink: {source}")
            destination = copied_kernel / name
            destination.write_bytes(source.read_bytes())
            origins[destination.relative_to(copied_world).as_posix()] = "source"

        generated = {
            "log.md": (
                "---\ntype: log\n---\n\n## Private E2E export\n\n"
                "Historical log entries intentionally omitted.\n"
            ),
            "tasks.json": '{"tasks": []}\n',
        }
        for name, content in generated.items():
            destination = copied_kernel / name
            destination.write_text(content, encoding="utf-8")
            origins[destination.relative_to(copied_world).as_posix()] = "generated"

    records = [
        file_record(copied_world, path, origins[path.relative_to(copied_world).as_posix()])
        for path in sorted(candidate for candidate in copied_world.rglob("*") if candidate.is_file())
    ]
    write_json(
        manifest_path,
        {
            "classification": classification,
            "export_profile": profile,
            "source_world_digest": tree_digest(source_world),
            "source_walnut_relative": walnut_relative.as_posix(),
            "files": records,
        },
    )
    return copied_world / walnut_relative, profile, records


def blocked(args: argparse.Namespace, reason: str, detail: str) -> int:
    evidence = {
        "status": "blocked",
        "reason": reason,
        "detail": detail,
        "classification": args.classification,
        "model": args.model or "",
        "private_context_sent": False,
    }
    write_json(args.evidence, evidence)
    print(json.dumps(evidence, sort_keys=True))
    return 77


def validate(args: argparse.Namespace) -> tuple[Path, Path]:
    if not args.codex_bin.is_file() or not os.access(args.codex_bin, os.X_OK):
        raise ValueError(f"Codex executable is missing or not executable: {args.codex_bin}")
    if not args.plugin_root.joinpath(".codex-plugin", "plugin.json").is_file():
        raise ValueError(f"plugin root is invalid: {args.plugin_root}")
    source_world = args.source_world.resolve()
    source_walnut = args.source_walnut.resolve()
    if source_world not in source_walnut.parents:
        raise ValueError("source walnut must be inside source world")
    if not source_world.joinpath(".alive").is_dir():
        raise ValueError("source world is missing .alive")
    for name in ("key.md", "log.md", "insights.md", "tasks.json"):
        if not source_walnut.joinpath("_kernel", name).is_file():
            raise ValueError(f"source walnut is missing _kernel/{name}")
    if args.run_root.exists():
        raise ValueError(f"run root already exists: {args.run_root}")
    return source_world, source_walnut


def output_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "phase": {"type": "string", "enum": ["save", "recover"]},
            "token": {"type": "string"},
            "decision_found": {"type": "boolean"},
            "task_found": {"type": "boolean"},
            "projection_found": {"type": "boolean"},
            "saved": {"type": "boolean"},
        },
        "required": [
            "phase",
            "token",
            "decision_found",
            "task_found",
            "projection_found",
            "saved",
        ],
    }


def run_codex(
    args: argparse.Namespace,
    *,
    phase: str,
    world: Path,
    prompt: str,
    schema: Path,
) -> dict[str, Any]:
    last_message = args.run_root / f"session-{'one' if phase == 'save' else 'two'}-last.json"
    events = args.run_root / f"session-{'one' if phase == 'save' else 'two'}-events.jsonl"
    stderr_path = args.run_root / f"session-{'one' if phase == 'save' else 'two'}-stderr.log"
    command = [
        str(args.codex_bin),
        "exec",
        "--ephemeral",
        "--json",
        "--color",
        "never",
        "--output-schema",
        str(schema),
        "--output-last-message",
        str(last_message),
        "--cd",
        str(world),
        "--skip-git-repo-check",
        "--sandbox",
        "workspace-write",
        "--dangerously-bypass-hook-trust",
    ]
    if args.local_provider:
        command.extend(["--oss", "--local-provider", args.local_provider])
    if args.model:
        command.extend(["--model", args.model])
    command.append(prompt)
    environment = dict(os.environ)
    environment["CODEX_HOME"] = str(args.codex_home)
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    try:
        stdout, stderr = process.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        events.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        return {
            "process_id": process.pid,
            "returncode": 124,
            "error": f"Codex {phase} session timed out after {args.timeout}s",
        }
    events.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    parsed: dict[str, Any] = {}
    if last_message.is_file():
        try:
            parsed = json.loads(last_message.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            parsed = {"parse_error": str(exc)}
    return {
        "process_id": process.pid,
        "returncode": process.returncode,
        "last_message": parsed,
        "events": str(events),
        "stderr": str(stderr_path),
    }


def disk_state(walnut: Path, token: str) -> dict[str, bool]:
    kernel = walnut / "_kernel"
    decision = f"Decision: preserve {token} across Codex sessions."
    task_title = f"Recover {token} in a new Codex session"
    log_path = kernel / "log.md"
    tasks_path = kernel / "tasks.json"
    now_path = kernel / "now.json"
    log = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
    tasks = tasks_path.read_text(encoding="utf-8") if tasks_path.is_file() else ""
    now = now_path.read_text(encoding="utf-8") if now_path.is_file() else ""
    return {
        "decision_found": decision in log,
        "task_found": task_title in tasks,
        "projection_found": token in now,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--plugin-root", type=Path, required=True)
    parser.add_argument("--source-world", type=Path, required=True)
    parser.add_argument("--source-walnut", type=Path, required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--classification", choices=("synthetic", "private"), default="private")
    parser.add_argument("--authorize-private-export", default="")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--local-provider", choices=("ollama", "lmstudio"))
    parser.add_argument("--token", required=True)
    parser.add_argument("--model")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    if (
        args.classification == "private"
        and not args.prepare_only
        and not args.local_provider
        and args.authorize_private_export != PRIVATE_AUTHORIZATION
    ):
        return blocked(
            args,
            "private_export_authorization_missing",
            "Private mode requires the exact --authorize-private-export acknowledgement.",
        )

    try:
        source_world, source_walnut = validate(args)
    except ValueError as exc:
        evidence = {"status": "fail", "reason": "invalid_input", "detail": str(exc)}
        write_json(args.evidence, evidence)
        print(json.dumps(evidence, sort_keys=True))
        return 2

    source_digest_before = tree_digest(source_world)
    args.run_root.mkdir(parents=True)
    copied_world = args.run_root / "World"
    disclosure_manifest = args.run_root / "disclosure-manifest.json"
    try:
        copied_walnut, export_profile, disclosed_files = export_world(
            source_world,
            source_walnut,
            copied_world,
            classification=args.classification,
            local_provider=args.local_provider,
            manifest_path=disclosure_manifest,
        )
    except ValueError as exc:
        evidence = {
            "status": "fail",
            "reason": "private_export_rejected",
            "detail": str(exc),
            "classification": args.classification,
            "private_context_sent": False,
        }
        write_json(args.evidence, evidence)
        print(json.dumps(evidence, sort_keys=True))
        return 2
    walnut_relative = source_walnut.relative_to(source_world)
    if args.prepare_only:
        evidence = {
            "status": "prepared",
            "reason": "minimum_disclosure_manifest_ready",
            "classification": args.classification,
            "export_profile": export_profile,
            "disclosure_manifest": str(disclosure_manifest),
            "disclosed_file_count": len(disclosed_files),
            "source_digest_before": source_digest_before,
            "source_digest_after": tree_digest(source_world),
            "copy_digest_after": tree_digest(copied_world),
            "model_transport": "none",
            "model": args.model or "",
            "private_context_sent": False,
        }
        write_json(args.evidence, evidence)
        print(json.dumps(evidence, sort_keys=True))
        return 0
    token = f"ALIVE_CODEX_E2E_{args.token}"
    schema_path = args.run_root / "response-schema.json"
    write_json(schema_path, output_schema())
    args.codex_home.mkdir(parents=True, exist_ok=True)

    transport_description = (
        f"local-only {args.local_provider}" if args.local_provider else "configured remote"
    )
    task_title = f"Recover {token} in a new Codex session"
    task_command = " ".join(
        (
            shlex.quote(sys.executable),
            shlex.quote(str(args.plugin_root.resolve() / "scripts" / "tasks.py")),
            "add",
            "--walnut",
            shlex.quote(str(copied_walnut)),
            "--title",
            shlex.quote(task_title),
            "--priority active",
            "--session codex-e2e",
        )
    )
    projection_command = " ".join(
        (
            shlex.quote(sys.executable),
            shlex.quote(str(args.plugin_root.resolve() / "scripts" / "project.py")),
            "--walnut",
            shlex.quote(str(copied_walnut)),
        )
    )
    session_one_prompt = f"""
SESSION_ONE model-backed ALIVE v3.3 E2E. This is an authorized
{args.classification} test world copy using the {transport_description} model
transport. Work only inside {copied_world}.
Load walnut {walnut_relative.as_posix()} by reading _kernel/key.md,
_kernel/now.json when present, and _kernel/insights.md. Then perform the
explicit ALIVE save workflow without asking follow-up questions:

1. Prepend a signed log entry containing this exact line:
   Decision: preserve {token} across Codex sessions.
2. Add this exact task by running the exact packaged command below once:
   {task_title}
   {task_command}
3. Regenerate _kernel/now.json by running this exact packaged command once:
   {projection_command}
4. Verify the decision, task, and token are physically present on disk.

Do not edit _kernel/tasks.json or _kernel/now.json directly. Do not search for
alternative task or projection tools; the exact packaged commands are above.
Do not create a token-named file or any other marker file. In the JSON response,
token must be the exact bare ALIVE_CODEX_E2E_ value shown above, with no path,
prefix, sentence, or punctuation. decision_found is true exactly when the exact
decision line is present in _kernel/log.md. task_found is true exactly when the
exact task title is present in _kernel/tasks.json. projection_found is true exactly when
the exact bare token is present in _kernel/now.json. Set phase to "save" and
saved to true only after all three checks succeed.

Return only the required JSON object. Do not merely claim success: the harness
will inspect disk before allowing session two to start.
""".strip()
    first = run_codex(
        args,
        phase="save",
        world=copied_world,
        prompt=session_one_prompt,
        schema=schema_path,
    )
    first_disk = disk_state(copied_walnut, token)
    first["disk"] = first_disk
    first["disk_saved"] = all(first_disk.values())
    if first["returncode"] != 0 or not first["disk_saved"]:
        evidence = {
            "status": "fail",
            "reason": "session_one_did_not_persist_required_state",
            "classification": args.classification,
            "token": token,
            "source_digest_before": source_digest_before,
            "source_digest_after": tree_digest(source_world),
            "session_one": first,
            "export_profile": export_profile,
            "disclosure_manifest": str(disclosure_manifest),
            "disclosed_file_count": len(disclosed_files),
            "model_transport": (
                f"local:{args.local_provider}" if args.local_provider else "openai"
            ),
            "model": args.model or "",
            "private_context_sent": (
                args.classification == "private" and not args.local_provider
            ),
        }
        write_json(args.evidence, evidence)
        print(json.dumps(evidence, sort_keys=True))
        return 1

    kernel_digest_after_save = tree_digest(copied_walnut / "_kernel")
    session_two_prompt = f"""
SESSION_TWO model-backed ALIVE v3.3 recovery proof. This is a new ephemeral
Codex process with no session-one transcript. Work only inside {copied_world}.
Load walnut {walnut_relative.as_posix()} by reading _kernel/log.md,
_kernel/tasks.json, and _kernel/now.json. Recover the unique E2E decision and
its matching recovery task that were saved by the previous process. Do not
infer or invent a value, do not inspect response-schema.json, and do not modify
the world. Field meanings are defined here: token must be the exact bare
ALIVE_CODEX_E2E_ value found in the saved records, with no path, prefix,
sentence, or punctuation. decision_found is true exactly when the exact
decision line is present in _kernel/log.md. task_found is true exactly when the
exact matching recovery task title is present in _kernel/tasks.json.
projection_found is true exactly when the exact bare token is present in
_kernel/now.json. Set phase to "recover" and saved to false because this
session performs no save. Return only the required JSON object.
""".strip()
    second = run_codex(
        args,
        phase="recover",
        world=copied_world,
        prompt=session_two_prompt,
        schema=schema_path,
    )
    response = second.get("last_message", {})
    second["decision_found"] = bool(response.get("decision_found"))
    second["task_found"] = bool(response.get("task_found"))
    second["projection_found"] = bool(response.get("projection_found"))
    second["token_matches"] = response.get("token") == token
    second["phase_matches"] = response.get("phase") == "recover"
    second["saved_is_false"] = response.get("saved") is False
    second["kernel_unchanged"] = (
        kernel_digest_after_save == tree_digest(copied_walnut / "_kernel")
    )
    source_digest_after = tree_digest(source_world)
    passed = (
        second["returncode"] == 0
        and second["decision_found"]
        and second["task_found"]
        and second["projection_found"]
        and second["token_matches"]
        and second["phase_matches"]
        and second["saved_is_false"]
        and second["kernel_unchanged"]
        and source_digest_before == source_digest_after
        and first["process_id"] != second["process_id"]
    )
    evidence = {
        "status": "pass" if passed else "fail",
        "reason": "verified" if passed else "session_two_recovery_mismatch",
        "classification": args.classification,
        "token": token,
        "codex_version": subprocess.run(
            [str(args.codex_bin), "--version"],
            text=True,
            capture_output=True,
            timeout=10,
        ).stdout.strip(),
        "plugin_root": str(args.plugin_root.resolve()),
        "source_digest_before": source_digest_before,
        "source_digest_after": source_digest_after,
        "copy_digest_after": tree_digest(copied_world),
        "ephemeral_sessions": True,
        "model_transport": (
            f"local:{args.local_provider}" if args.local_provider else "openai"
        ),
        "model": args.model or "",
        "export_profile": export_profile,
        "disclosure_manifest": str(disclosure_manifest),
        "disclosed_file_count": len(disclosed_files),
        "session_one": first,
        "session_two": second,
        "private_context_sent": (
            args.classification == "private" and not args.local_provider
        ),
    }
    write_json(args.evidence, evidence)
    print(json.dumps(evidence, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
