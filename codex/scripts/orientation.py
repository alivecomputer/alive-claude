#!/usr/bin/env python3
"""Build, validate, and render ALIVE's bounded Codex orientation cache."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


SCHEMA_VERSION = 1
MAX_BYTES = 8192
MAX_RECOMMENDATIONS = 9
MAX_RENDERED_RECOMMENDATIONS = 3
OPEN_STATUSES = {"todo", "active", "waiting", "scheduled", "blocked"}
SEVERITY_ORDER = {"critical": 0, "warning": 1, "notice": 2}
CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}
SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "target",
    "_archive",
    "_references",
    "01_Archive",
    "raw",
}
RELATIVE_DATES = {
    "today": lambda created: created,
    "tomorrow": lambda created: created + timedelta(days=1),
    "this weekend": lambda created: created
    + timedelta(days=(6 - created.weekday()) % 7),
    "next week": lambda created: created + timedelta(days=7),
}
WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
TASK_REQUIRED_TEXT_FIELDS = ("id", "title", "status", "created")
TASK_OPTIONAL_TEXT_FIELDS = ("priority", "due", "assignee")
TOP_LEVEL_FIELDS = {
    "schema_version",
    "generated",
    "source_index",
    "world",
    "health",
    "recommendations",
    "counts",
}
SOURCE_INDEX_FIELDS = {"generated", "generation", "digest", "size", "mtime_ns"}
WORLD_FIELDS = {"root", "walnuts", "people", "unrouted_inputs"}
HEALTH_FIELDS = {
    "index_valid",
    "projection_stale",
    "issue_count",
    "malformed_source_count",
}
COUNT_FIELDS = {"total_detected", "shown", "malformed_sources"}
RECOMMENDATION_FIELDS = {
    "id",
    "kind",
    "severity",
    "confidence",
    "walnut",
    "task_id",
    "summary",
    "evidence",
    "proposed_action",
    "can_run_now",
}
EVIDENCE_FIELDS = {"path", "created", "status"}


def compact_json(payload: object) -> bytes:
    return json.dumps(
        payload, separators=(",", ":"), ensure_ascii=False, sort_keys=True
    ).encode("utf-8")


def parse_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def valid_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def clipped(value: str, limit: int) -> str:
    text = value.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def strict_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def index_count(stats: object, field: str) -> int:
    value = stats.get(field, 0) if isinstance(stats, dict) else 0
    return value if strict_nonnegative_int(value) else 0


def valid_index_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if not valid_timestamp(payload.get("generated")):
        return False
    generation = payload.get("generation")
    if not isinstance(generation, str) or not re.fullmatch(
        r"[a-f0-9]{32}", generation
    ):
        return False
    stats = payload.get("stats")
    if not isinstance(stats, dict) or not all(
        strict_nonnegative_int(stats.get(field, 0))
        for field in (
            "walnuts",
            "people",
            "capsules",
            "sessions",
            "inputs",
            "unsigned_with_stash",
        )
    ):
        return False
    walnuts = payload.get("walnuts")
    people = payload.get("people")
    recent_sessions = payload.get("recent_sessions")
    if not all(isinstance(value, list) for value in (walnuts, people, recent_sessions)):
        return False
    for walnut in walnuts:
        if not isinstance(walnut, dict) or not isinstance(walnut.get("path"), str):
            return False
        if "name" in walnut and not isinstance(walnut["name"], str):
            return False
        if "archived" in walnut and type(walnut["archived"]) is not bool:
            return False
    return all(isinstance(item, dict) for item in people + recent_sessions)


def open_task(task: dict) -> bool:
    return task["status"].strip().lower() in OPEN_STATUSES


def discover_task_files(walnut_root: Path) -> list[Path]:
    """Find task files without entering archives, hidden paths, or child walnuts."""
    results: list[Path] = []
    walnut_root = walnut_root.resolve()
    for root, dirs, files in os.walk(walnut_root):
        root_path = Path(root)
        dirs[:] = [
            name
            for name in dirs
            if not name.startswith(".") and name not in SKIP_DIRS
        ]
        if root_path != walnut_root and root_path.joinpath(
            "_kernel", "key.md"
        ).is_file():
            dirs[:] = []
            continue
        if "tasks.json" in files:
            results.append(root_path / "tasks.json")
    return sorted(results)


def valid_task_record(task: object) -> bool:
    if not isinstance(task, dict):
        return False
    for field in TASK_REQUIRED_TEXT_FIELDS:
        if not isinstance(task.get(field), str):
            return False
    for field in TASK_OPTIONAL_TEXT_FIELDS:
        if field in task and task[field] is not None and not isinstance(task[field], str):
            return False
    return True


def scan_task_records(
    world_root: Path, index_payload: dict
) -> tuple[list[dict], list[str]]:
    """Return valid task records plus deterministic path-only malformed sources."""
    records: list[dict] = []
    malformed: set[str] = set()
    resolved_world = world_root.resolve()
    walnuts = index_payload.get("walnuts", [])
    if not isinstance(walnuts, list):
        return records, malformed
    for walnut in walnuts:
        if not isinstance(walnut, dict):
            continue
        relative = walnut.get("path")
        if not isinstance(relative, str) or not relative:
            continue
        if walnut.get("archived") is True or "01_Archive" in Path(relative).parts:
            continue
        walnut_root = (resolved_world / relative).resolve()
        try:
            walnut_root.relative_to(resolved_world)
        except ValueError:
            continue
        if not walnut_root.is_dir():
            continue
        walnut_name = walnut.get("name")
        if not isinstance(walnut_name, str):
            walnut_name = walnut_root.name
        for tasks_file in discover_task_files(walnut_root):
            relative_source = tasks_file.relative_to(resolved_world).as_posix()
            try:
                raw = tasks_file.read_bytes()
                payload = json.loads(raw.decode("utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                malformed.add(relative_source)
                continue
            if not isinstance(payload, dict) or not isinstance(
                payload.get("tasks"), list
            ):
                malformed.add(relative_source)
                continue
            tasks = payload["tasks"]
            if not all(valid_task_record(task) for task in tasks):
                malformed.add(relative_source)
                continue
            records.extend(
                {
                    "walnut": clipped(walnut_name, 80),
                    "path": relative_source,
                    "task": task,
                }
                for task in tasks
            )
    return records, sorted(malformed)


def task_recommendation(
    record: dict,
    *,
    kind: str,
    severity: str,
    summary: str,
    sort_date: str,
    proposed_action: str = "review_task",
) -> dict:
    task = record["task"]
    task_id = clipped(task["id"], 80)
    walnut = clipped(record["walnut"], 80)
    slug = kind.replace("_", "-")
    item = {
        "id": f"task:{walnut}:{task_id}:{slug}",
        "kind": kind,
        "severity": severity,
        "confidence": "high",
        "walnut": walnut,
        "task_id": task_id,
        "summary": clipped(summary, 180),
        "evidence": {
            "path": clipped(record["path"], 180),
            "created": clipped(task["created"], 32),
            "status": clipped(task["status"], 32),
        },
        "proposed_action": proposed_action,
        "can_run_now": False,
        "sort_date": sort_date,
    }
    if len(item["id"]) > 180:
        digest = hashlib.sha256(item["id"].encode("utf-8")).hexdigest()[:12]
        item["id"] = item["id"][:167] + ":" + digest
    return item


def malformed_recommendation(path: str) -> dict:
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:16]
    return {
        "id": f"source:{digest}:malformed",
        "kind": "malformed_source",
        "severity": "warning",
        "confidence": "high",
        "walnut": "",
        "task_id": "",
        "summary": "Malformed task source requires repair",
        "evidence": {
            "path": clipped(path, 180),
            "created": "",
            "status": "",
        },
        "proposed_action": "repair_source",
        "can_run_now": False,
        "sort_date": "",
    }


def expired_relative_date(record: dict, today: date) -> dict | None:
    task = record["task"]
    if not open_task(task):
        return None
    created = parse_date(task["created"])
    if created is None:
        return None
    title = task["title"].lower()
    matches: list[tuple[str, date]] = []
    for term, target_for in RELATIVE_DATES.items():
        if re.search(r"\b" + re.escape(term) + r"\b", title):
            matches.append((term, target_for(created)))
    for weekday, weekday_number in WEEKDAYS.items():
        if re.search(r"\b" + weekday + r"\b", title):
            days = (weekday_number - created.weekday()) % 7
            matches.append((weekday, created + timedelta(days=days)))
    if not matches:
        return None
    term, target = min(matches, key=lambda match: match[1])
    if target >= today:
        return None
    age = (today - target).days
    return task_recommendation(
        record,
        kind="expired_relative_date",
        severity="warning",
        summary=f'"{term}" is {age} days old',
        sort_date=target.isoformat(),
    )


def overdue(record: dict, today: date) -> dict | None:
    task = record["task"]
    due = parse_date(task.get("due"))
    if not open_task(task) or due is None or due >= today:
        return None
    return task_recommendation(
        record,
        kind="overdue",
        severity="critical",
        summary=f"Due date was {(today - due).days} days ago",
        sort_date=due.isoformat(),
    )


def blocked_status_mismatch(record: dict, today: date) -> dict | None:
    task = record["task"]
    status = task["status"].strip().lower()
    title = task["title"].lower()
    if status not in {"todo", "active"} or not re.search(
        r"\b(blocked|waiting)\b", title
    ):
        return None
    return task_recommendation(
        record,
        kind="blocked_status_mismatch",
        severity="warning",
        summary="Title indicates waiting or blocked, but status is still open",
        sort_date=task["created"],
    )


def completed_status_mismatch(record: dict, today: date) -> dict | None:
    task = record["task"]
    if not open_task(task) or not re.search(
        r"\b(complete(?:d)?|done|shipped|cancelled)\b", task["title"].lower()
    ):
        return None
    return task_recommendation(
        record,
        kind="completed_status_mismatch",
        severity="warning",
        summary="Title indicates completion, but formal status remains open",
        sort_date=task["created"],
    )


def urgent_unowned(record: dict, today: date) -> dict | None:
    task = record["task"]
    if not open_task(task) or (task.get("priority") or "").strip().lower() != "urgent":
        return None
    if task.get("assignee") or task.get("due"):
        return None
    return task_recommendation(
        record,
        kind="urgent_unowned",
        severity="notice",
        summary="Urgent task has neither an assignee nor a due date",
        sort_date=task["created"],
    )


DETECTORS = (
    expired_relative_date,
    overdue,
    blocked_status_mismatch,
    completed_status_mismatch,
    urgent_unowned,
)


def rank_key(item: dict) -> tuple[int, int, str, str]:
    return (
        SEVERITY_ORDER[item["severity"]],
        CONFIDENCE_ORDER[item["confidence"]],
        item.get("sort_date", "9999-12-31"),
        item["id"],
    )


def index_identity(index_path: Path, index_payload: dict) -> dict:
    raw = index_path.read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    if parsed != index_payload:
        raise ValueError("index payload does not match committed _index.json")
    if not valid_index_payload(parsed):
        raise ValueError("index source is invalid")
    generated = parsed.get("generated")
    generation = parsed.get("generation")
    if not valid_timestamp(generated):
        raise ValueError("index generated timestamp is invalid")
    if not isinstance(generation, str) or not re.fullmatch(
        r"[a-f0-9]{32}", generation
    ):
        raise ValueError("index generation marker is invalid")
    stat = index_path.stat()
    return {
        "generated": generated,
        "generation": generation,
        "digest": hashlib.sha256(raw).hexdigest(),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def build_orientation(
    world_root: Path,
    index_payload: dict,
    today: date,
    *,
    index_path: Path | None = None,
) -> dict:
    """Build a bounded projection from a committed index and strict task sources."""
    source_path = index_path or world_root / ".alive" / "_index.json"
    source_identity = index_identity(source_path, index_payload)
    records, malformed_paths = scan_task_records(world_root, index_payload)
    recommendations = [
        item
        for record in records
        for detector in DETECTORS
        if (item := detector(record, today)) is not None
    ]
    recommendations.extend(malformed_recommendation(path) for path in malformed_paths)
    recommendations.sort(key=rank_key)
    total_detected = len(recommendations)
    selected = recommendations[:MAX_RECOMMENDATIONS]
    for item in selected:
        item.pop("sort_date", None)
    walnuts = index_payload.get("walnuts", [])
    stats = index_payload.get("stats", {})
    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated": utc_timestamp(),
        "source_index": source_identity,
        "world": {
            "root": clipped(str(world_root.resolve()), 180),
            "walnuts": len(walnuts) if isinstance(walnuts, list) else 0,
            "people": index_count(stats, "people"),
            "unrouted_inputs": index_count(stats, "inputs"),
        },
        "health": {
            "index_valid": True,
            "projection_stale": False,
            "issue_count": total_detected,
            "malformed_source_count": len(malformed_paths),
        },
        "recommendations": selected,
        "counts": {
            "total_detected": total_detected,
            "shown": len(selected),
            "malformed_sources": len(malformed_paths),
        },
    }
    while selected and len(compact_json(payload)) > MAX_BYTES:
        selected.pop()
        payload["counts"]["shown"] = len(selected)
    if len(compact_json(payload)) > MAX_BYTES:
        raise ValueError("orientation exceeds 8192 bytes")
    if validate_orientation(payload) is None:
        raise ValueError("generated orientation failed strict schema validation")
    return payload


def atomic_write_json(path: Path, payload: dict) -> None:
    encoded = compact_json(payload)
    if len(encoded) > MAX_BYTES:
        raise ValueError("orientation exceeds 8192 bytes")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def build_and_write(
    world_root: Path,
    index_payload: dict,
    today: date | None = None,
    *,
    index_path: Path | None = None,
) -> dict:
    if os.environ.get("ALIVE_ORIENTATION_TEST_FAIL"):
        raise RuntimeError("ALIVE_ORIENTATION_TEST_FAIL requested")
    payload = build_orientation(
        world_root,
        index_payload,
        today or date.today(),
        index_path=index_path,
    )
    atomic_write_json(world_root / ".alive" / "_orientation.json", payload)
    return payload


def valid_recommendation(item: object) -> bool:
    if not isinstance(item, dict) or set(item) != RECOMMENDATION_FIELDS:
        return False
    text_limits = {
        "id": 180,
        "kind": 80,
        "walnut": 80,
        "task_id": 80,
        "summary": 180,
        "proposed_action": 80,
    }
    for field, limit in text_limits.items():
        value = item.get(field)
        if not isinstance(value, str) or len(value) > limit:
            return False
    if not item["id"] or not item["kind"] or not item["summary"] or not item[
        "proposed_action"
    ]:
        return False
    if item.get("severity") not in SEVERITY_ORDER:
        return False
    if item.get("confidence") not in CONFIDENCE_ORDER:
        return False
    if type(item.get("can_run_now")) is not bool:
        return False
    evidence = item.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != EVIDENCE_FIELDS:
        return False
    for field, limit in (("path", 180), ("created", 32), ("status", 32)):
        value = evidence.get(field)
        if not isinstance(value, str) or len(value) > limit:
            return False
    return bool(evidence["path"])


def validate_orientation(payload: object) -> dict | None:
    """The single strict schema-1 validator used by render, save, and doctor."""
    if (
        not isinstance(payload, dict)
        or set(payload) != TOP_LEVEL_FIELDS
        or len(compact_json(payload)) > MAX_BYTES
    ):
        return None
    if type(payload.get("schema_version")) is not int or payload[
        "schema_version"
    ] != SCHEMA_VERSION:
        return None
    if not valid_timestamp(payload.get("generated")):
        return None

    source = payload.get("source_index")
    if not isinstance(source, dict) or set(source) != SOURCE_INDEX_FIELDS:
        return None
    if not valid_timestamp(source.get("generated")):
        return None
    if not isinstance(source.get("generation"), str) or not re.fullmatch(
        r"[a-f0-9]{32}", source["generation"]
    ):
        return None
    if not isinstance(source.get("digest"), str) or not re.fullmatch(
        r"[a-f0-9]{64}", source["digest"]
    ):
        return None
    if not strict_nonnegative_int(source.get("size")) or source["size"] == 0:
        return None
    if not strict_nonnegative_int(source.get("mtime_ns")):
        return None

    world = payload.get("world")
    if (
        not isinstance(world, dict)
        or set(world) != WORLD_FIELDS
        or not isinstance(world.get("root"), str)
    ):
        return None
    if not world["root"] or len(world["root"]) > 180:
        return None
    if not all(
        strict_nonnegative_int(world.get(field))
        for field in ("walnuts", "people", "unrouted_inputs")
    ):
        return None

    health = payload.get("health")
    if not isinstance(health, dict) or set(health) != HEALTH_FIELDS:
        return None
    if health.get("index_valid") is not True:
        return None
    if type(health.get("projection_stale")) is not bool:
        return None
    if not strict_nonnegative_int(health.get("issue_count")):
        return None
    if not strict_nonnegative_int(health.get("malformed_source_count")):
        return None

    recommendations = payload.get("recommendations")
    if (
        not isinstance(recommendations, list)
        or len(recommendations) > MAX_RECOMMENDATIONS
        or not all(valid_recommendation(item) for item in recommendations)
    ):
        return None

    counts = payload.get("counts")
    if not isinstance(counts, dict) or set(counts) != COUNT_FIELDS:
        return None
    if not all(
        strict_nonnegative_int(counts.get(field))
        for field in ("total_detected", "shown", "malformed_sources")
    ):
        return None
    if counts["shown"] != len(recommendations):
        return None
    if counts["total_detected"] < counts["shown"]:
        return None
    if health["issue_count"] != counts["total_detected"]:
        return None
    if health["malformed_source_count"] != counts["malformed_sources"]:
        return None
    if counts["malformed_sources"] > counts["total_detected"]:
        return None
    return payload


def validate_orientation_for_world(
    payload: object, world_root: Path, *, identity_mode: str
) -> dict | None:
    valid = validate_orientation(payload)
    if valid is None or identity_mode not in {"stat", "digest"}:
        return None
    if valid["world"]["root"] != clipped(str(world_root.resolve()), 180):
        return None
    index_path = world_root / ".alive" / "_index.json"
    try:
        stat = index_path.stat()
    except OSError:
        return None
    source = valid["source_index"]
    if stat.st_size != source["size"] or stat.st_mtime_ns != source["mtime_ns"]:
        return None
    if identity_mode == "stat":
        return valid
    try:
        raw = index_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["digest"]:
            return None
        index_payload = json.loads(raw.decode("utf-8"))
        yaml_payload = json.loads(
            (world_root / ".alive" / "_index.yaml").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(index_payload, dict) or index_payload != yaml_payload:
        return None
    if index_payload.get("generated") != source["generated"]:
        return None
    if index_payload.get("generation") != source["generation"]:
        return None
    return valid


def render_orientation(
    payload: dict, limit: int = MAX_RENDERED_RECOMMENDATIONS
) -> str:
    """Render a small summary only after the strict schema has passed."""
    valid = validate_orientation(payload)
    if valid is None:
        return ""
    count = valid["health"]["issue_count"]
    lines = [f"ALIVE found {count} things needing attention."]
    shown = valid["recommendations"][
        : max(0, min(limit, MAX_RENDERED_RECOMMENDATIONS))
    ]
    for number, item in enumerate(shown, start=1):
        suffix = f" ({item['walnut']})" if item["walnut"] else ""
        lines.append(f"{number}. {item['summary']}{suffix}")
    return "\n".join(lines)


def read_orientation(world_root: Path) -> dict:
    path = world_root / ".alive" / "_orientation.json"
    encoded = path.read_bytes()
    if len(encoded) > MAX_BYTES:
        raise ValueError("orientation exceeds 8192 bytes")
    payload = json.loads(encoded.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("orientation root must be an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("build")
    build.add_argument("world_root", type=Path)
    build.add_argument("--today", type=date.fromisoformat)
    render = subcommands.add_parser("render")
    render.add_argument("world_root", type=Path)
    render.add_argument("--limit", type=int, default=MAX_RENDERED_RECOMMENDATIONS)
    validate = subcommands.add_parser("validate")
    validate.add_argument("world_root", type=Path)
    validate.add_argument(
        "--identity-mode", choices=("stat", "digest"), default="digest"
    )
    args = parser.parse_args()
    try:
        if args.command == "build":
            index_path = args.world_root / ".alive" / "_index.json"
            index_payload = json.loads(index_path.read_text(encoding="utf-8"))
            if not isinstance(index_payload, dict):
                raise ValueError("index root must be an object")
            build_and_write(
                args.world_root,
                index_payload,
                args.today,
                index_path=index_path,
            )
            return 0
        payload = read_orientation(args.world_root)
        identity_mode = (
            args.identity_mode if args.command == "validate" else "stat"
        )
        valid = validate_orientation_for_world(
            payload, args.world_root, identity_mode=identity_mode
        )
        if valid is None:
            raise ValueError(
                f"orientation failed strict schema or {identity_mode} index identity"
            )
        if args.command == "validate":
            print(
                json.dumps(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "identity_mode": identity_mode,
                        "generation": valid["source_index"]["generation"],
                    },
                    sort_keys=True,
                )
            )
            return 0
        output = render_orientation(valid, args.limit)
        if not output:
            raise ValueError("orientation cannot be rendered")
        print(output)
        return 0
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        RuntimeError,
        ValueError,
    ) as error:
        parser.error(str(error))


if __name__ == "__main__":
    raise SystemExit(main())
