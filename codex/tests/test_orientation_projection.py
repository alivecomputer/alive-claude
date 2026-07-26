from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


ORIENTATION = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "alive"
    / "scripts"
    / "orientation.py"
)


def load_orientation_module():
    spec = importlib.util.spec_from_file_location("alive_orientation", ORIENTATION)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load orientation module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class OrientationProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.world = Path(self.temporary_directory.name)
        self.walnut = self.world / "04_Ventures" / "example"
        self.walnut.joinpath("_kernel").mkdir(parents=True)
        self.index = {
            "generated": "2026-07-25T01:02:03.456789Z",
            "generation": "0123456789abcdef0123456789abcdef",
            "stats": {"people": 2, "inputs": 3},
            "walnuts": [
                {"name": "example", "path": "04_Ventures/example"},
            ],
            "people": [],
            "recent_sessions": [],
        }
        self.alive = self.world / ".alive"
        self.alive.mkdir()
        self.write_index()

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_tasks(self, tasks: list[dict]) -> None:
        self.walnut.joinpath("_kernel", "tasks.json").write_text(
            json.dumps({"tasks": tasks}), encoding="utf-8"
        )

    def write_index(self) -> None:
        encoded = json.dumps(self.index, ensure_ascii=False)
        self.alive.joinpath("_index.json").write_text(encoded, encoding="utf-8")
        self.alive.joinpath("_index.yaml").write_text(encoded, encoding="utf-8")

    def write_many_defective_tasks(self, count: int) -> None:
        self.write_tasks(
            [
                {
                    "id": f"t{number:03d}",
                    "title": f"Call them tomorrow {number}",
                    "status": "todo",
                    "priority": "active",
                    "created": "2026-05-14",
                }
                for number in range(count)
            ]
        )

    def build(self, *, today: date) -> dict:
        return load_orientation_module().build_orientation(
            self.world, self.index, today, index_path=self.alive / "_index.json"
        )

    def test_detects_expired_dates_overdue_and_status_contradictions(self):
        """Removing a deterministic detector should hide its matching exception."""
        self.write_tasks([
            {"id": "t001", "title": "Call them tomorrow", "status": "todo",
             "priority": "urgent", "created": "2026-05-14"},
            {"id": "t002", "title": "Submit invoice", "status": "active",
             "priority": "active", "created": "2026-07-01", "due": "2026-07-20"},
            {"id": "t003", "title": "Waiting: Dave to reply", "status": "todo",
             "priority": "urgent", "created": "2026-07-24"},
            {"id": "t004", "title": "Strategy phase COMPLETE", "status": "active",
             "priority": "active", "created": "2026-07-24"},
        ])
        payload = self.build(today=date(2026, 7, 25))
        kinds = [item["kind"] for item in payload["recommendations"]]
        self.assertIn("expired_relative_date", kinds)
        self.assertIn("overdue", kinds)
        self.assertIn("blocked_status_mismatch", kinds)
        self.assertIn("completed_status_mismatch", kinds)

    def test_age_alone_does_not_call_a_task_dead(self):
        """A long-running owned task without a due date must not be proposed for removal."""
        self.write_tasks([{
            "id": "t001", "title": "Long-running research", "status": "active",
            "priority": "active", "created": "2026-01-01",
            "assignee": "Ben", "due": None,
        }])
        payload = self.build(today=date(2026, 7, 25))
        self.assertFalse(any("dead" in item["kind"] for item in payload["recommendations"]))
        self.assertFalse(any(item.get("proposed_action") == "drop_task"
                             for item in payload["recommendations"]))

    def test_projection_is_bounded_and_deterministic(self):
        """Changing input order cannot produce more than nine whole recommendations."""
        self.write_many_defective_tasks(40)
        orientation = load_orientation_module()
        first = orientation.build_orientation(self.world, self.index, date(2026, 7, 25))
        second = orientation.build_orientation(self.world, self.index, date(2026, 7, 25))
        self.assertEqual(first["recommendations"], second["recommendations"])
        self.assertLessEqual(len(first["recommendations"]), 9)
        encoded = json.dumps(first, separators=(",", ":")).encode()
        self.assertLessEqual(len(encoded), 8192)
        self.assertLessEqual(len(orientation.render_orientation(first).encode()), 8192)
        self.assertEqual(40, first["counts"]["total_detected"])

    def test_relative_date_without_a_valid_created_date_is_ignored(self):
        """Removing the created-date guard would create a context-free relative-date alert."""
        self.write_tasks([{
            "id": "t001", "title": "Call them tomorrow", "status": "todo",
            "priority": "urgent", "created": "not-a-date",
        }])
        payload = self.build(today=date(2026, 7, 25))
        self.assertNotIn(
            "expired_relative_date",
            [item["kind"] for item in payload["recommendations"]],
        )

    def test_oversized_metadata_fails_without_replacing_previous_projection(self):
        """Removing the final size gate could replace a valid cached orientation with an invalid one."""
        orientation = load_orientation_module()
        destination = self.alive / "_orientation.json"
        destination.write_text('{"sentinel":true}', encoding="utf-8")
        oversized_index = {
            "generated": "2026-07-25T01:02:03.456789Z",
            "generation": "fedcba9876543210fedcba9876543210",
            "stats": {"people": 10 ** 4000, "inputs": 10 ** 4000},
            "walnuts": [],
            "people": [],
            "recent_sessions": [],
        }
        self.index = oversized_index
        self.write_index()
        with self.assertRaisesRegex(ValueError, "exceeds 8192 bytes"):
            orientation.build_and_write(
                self.world,
                oversized_index,
                date(2026, 7, 25),
                index_path=self.alive / "_index.json",
            )
        self.assertEqual('{"sentinel":true}', destination.read_text(encoding="utf-8"))

    def test_build_rejects_malformed_index_container_shapes(self):
        """index_valid=true must mean the source index passed its container contract."""
        orientation = load_orientation_module()
        malformed = {
            "generated": "2026-07-25T01:02:03.456789Z",
            "generation": "0123456789abcdef0123456789abcdef",
            "stats": [],
            "walnuts": {},
            "people": {},
            "recent_sessions": {},
        }
        self.index = malformed
        self.write_index()
        orientation.scan_task_records = lambda *_args, **_kwargs: self.fail(
            "invalid index containers must be rejected before task discovery"
        )
        with self.assertRaisesRegex(ValueError, "index.*invalid"):
            orientation.build_orientation(
                self.world,
                malformed,
                date(2026, 7, 25),
                index_path=self.alive / "_index.json",
            )

    def test_relative_date_boundaries_end_on_sunday_and_allow_same_day_weekdays(self):
        """Changing weekend end or same-day weekday anchors hides or prematurely raises exceptions."""
        self.write_tasks([
            {"id": "t001", "title": "Finish this weekend", "status": "todo",
             "priority": "active", "created": "2026-07-24"},
            {"id": "t002", "title": "Plan this weekend", "status": "todo",
             "priority": "active", "created": "2026-07-26"},
            {"id": "t003", "title": "Call them on Monday", "status": "todo",
             "priority": "active", "created": "2026-07-20"},
        ])
        sunday = self.build(today=date(2026, 7, 26))
        self.assertNotIn(
            "t001",
            [item["task_id"] for item in sunday["recommendations"]],
        )
        monday = self.build(today=date(2026, 7, 27))
        expired_task_ids = {
            item["task_id"]
            for item in monday["recommendations"]
            if item["kind"] == "expired_relative_date"
        }
        self.assertEqual({"t001", "t002", "t003"}, expired_task_ids)

    def test_build_cli_writes_and_render_cli_bounds_output(self):
        """Removing atomic build output or render validation breaks the public CLI contract."""
        self.write_tasks([{
            "id": "t001", "title": "Submit invoice", "status": "active",
            "priority": "active", "created": "2026-07-01", "due": "2026-07-20",
        }])
        built = subprocess.run(
            [sys.executable, str(ORIENTATION), "build", str(self.world), "--today", "2026-07-25"],
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(0, built.returncode, built.stderr)
        payload = json.loads(
            self.alive.joinpath("_orientation.json").read_text(encoding="utf-8")
        )
        self.assertEqual(1, payload["schema_version"])
        rendered = subprocess.run(
            [sys.executable, str(ORIENTATION), "render", str(self.world), "--limit", "1"],
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(0, rendered.returncode, rendered.stderr)
        self.assertEqual(2, len(rendered.stdout.strip().splitlines()))

    def test_strict_schema_rejects_minimal_fake_and_bad_nested_types(self):
        """Render/save/doctor must not accept a shape that merely says schema 1."""
        orientation = load_orientation_module()
        minimal = {
            "schema_version": 1,
            "health": {},
            "counts": {},
            "recommendations": [],
        }
        self.assertIsNone(orientation.validate_orientation(minimal))

        self.write_tasks([])
        valid = self.build(today=date(2026, 7, 25))
        self.assertIsNotNone(orientation.validate_orientation(valid))
        mutations = [
            ("boolean schema", lambda value: value.__setitem__("schema_version", True)),
            ("bad generated", lambda value: value.__setitem__("generated", "today")),
            ("bad world count", lambda value: value["world"].__setitem__("walnuts", True)),
            ("false index health", lambda value: value["health"].__setitem__("index_valid", False)),
            ("bad issue count", lambda value: value["health"].__setitem__("issue_count", "0")),
            ("bad shown count", lambda value: value["counts"].__setitem__("shown", 1)),
            ("bad source digest", lambda value: value["source_index"].__setitem__("digest", "x")),
            ("unknown top field", lambda value: value.__setitem__("private", "secret")),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label):
                candidate = json.loads(json.dumps(valid))
                mutate(candidate)
                self.assertIsNone(orientation.validate_orientation(candidate))

        with_recommendation = self.build(today=date(2026, 7, 25))
        if not with_recommendation["recommendations"]:
            self.write_tasks(
                [
                    {
                        "id": "t001",
                        "title": "Submit invoice",
                        "status": "active",
                        "priority": "active",
                        "created": "2026-07-01",
                        "due": "2026-07-20",
                    }
                ]
            )
            with_recommendation = self.build(today=date(2026, 7, 25))
        with_recommendation["recommendations"][0]["private"] = "secret"
        self.assertIsNone(orientation.validate_orientation(with_recommendation))

    def test_malformed_task_sources_emit_path_only_health_without_hostile_content(self):
        """Malformed task data must surface deterministically without entering context."""
        hostile = "PRIVATE-HOSTILE-CONTENT-DO-NOT-RENDER"
        cases: list[tuple[str, bytes]] = [
            ("invalid-json/tasks.json", b"{not json " + hostile.encode()),
            ("invalid-utf8/tasks.json", b'{"tasks":[]}\xff'),
            ("root-list/tasks.json", b"[]"),
            ("tasks-object/tasks.json", b'{"tasks":{}}'),
            (
                "hostile-fields/tasks.json",
                json.dumps(
                    {
                        "tasks": [
                            {
                                "id": {"secret": hostile},
                                "title": hostile,
                                "status": "todo",
                                "created": "2026-01-01",
                            }
                        ]
                    }
                ).encode(),
            ),
        ]
        bundle_paths = []
        for relative, raw in cases:
            path = self.walnut / relative
            path.parent.mkdir(parents=True)
            path.write_bytes(raw)
            bundle_paths.append(path.relative_to(self.world).as_posix())
        self.walnut.joinpath("_kernel", "tasks.json").unlink(missing_ok=True)

        payload = self.build(today=date(2026, 7, 25))
        malformed = [
            item for item in payload["recommendations"]
            if item["kind"] == "malformed_source"
        ]
        self.assertEqual(sorted(bundle_paths), sorted(item["evidence"]["path"] for item in malformed))
        self.assertEqual(len(cases), payload["health"]["malformed_source_count"])
        encoded = json.dumps(payload, ensure_ascii=False)
        rendered = load_orientation_module().render_orientation(payload)
        self.assertNotIn(hostile, encoded)
        self.assertNotIn(hostile, rendered)
        self.assertIn("Malformed task source", rendered)

    def test_archived_walnuts_and_archive_subtrees_are_excluded(self):
        """Archived tasks must not become current recommendations."""
        archive_walnut = self.world / "01_Archive" / "04_Ventures" / "old"
        archive_walnut.joinpath("_kernel").mkdir(parents=True)
        archive_walnut.joinpath("_kernel", "tasks.json").write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "id": "t999",
                            "title": "Submit invoice",
                            "status": "active",
                            "priority": "urgent",
                            "created": "2026-01-01",
                            "due": "2026-01-02",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        self.walnut.joinpath("01_Archive", "bundle").mkdir(parents=True)
        self.walnut.joinpath("01_Archive", "bundle", "tasks.json").write_text(
            archive_walnut.joinpath("_kernel", "tasks.json").read_text(),
            encoding="utf-8",
        )
        self.index["walnuts"].extend(
            [
                {
                    "name": "old",
                    "path": "01_Archive/04_Ventures/old",
                    "archived": True,
                },
                {
                    "name": "archived-flag",
                    "path": "04_Ventures/example",
                    "archived": True,
                },
            ]
        )
        self.write_index()
        self.write_tasks([])
        payload = self.build(today=date(2026, 7, 25))
        self.assertEqual([], payload["recommendations"])

    def test_orientation_identity_detects_missing_touched_and_copied_stale_index(self):
        """Stat-only startup and digest-strict save/doctor must bind cache to its index."""
        self.write_tasks([])
        orientation = load_orientation_module()
        payload = orientation.build_and_write(
            self.world,
            self.index,
            date(2026, 7, 25),
            index_path=self.alive / "_index.json",
        )
        self.assertIsNotNone(
            orientation.validate_orientation_for_world(
                payload, self.world, identity_mode="digest"
            )
        )
        wrong_world = json.loads(json.dumps(payload))
        wrong_world["world"]["root"] = str(self.world / "other")
        self.assertIsNone(
            orientation.validate_orientation_for_world(
                wrong_world, self.world, identity_mode="stat"
            )
        )

        original_index = self.alive.joinpath("_index.json").read_bytes()
        stat = self.alive.joinpath("_index.json").stat()
        os.utime(
            self.alive / "_index.json",
            ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000),
        )
        self.assertIsNone(
            orientation.validate_orientation_for_world(
                payload, self.world, identity_mode="stat"
            )
        )

        self.alive.joinpath("_index.json").write_bytes(original_index)
        os.utime(
            self.alive / "_index.json",
            ns=(stat.st_atime_ns, stat.st_mtime_ns),
        )
        copied = json.loads(original_index)
        copied["stats"]["people"] = 9
        replacement = json.dumps(copied, ensure_ascii=False).encode()
        self.assertEqual(len(original_index), len(replacement))
        self.alive.joinpath("_index.json").write_bytes(replacement)
        os.utime(
            self.alive / "_index.json",
            ns=(stat.st_atime_ns, stat.st_mtime_ns),
        )
        self.assertIsNotNone(
            orientation.validate_orientation_for_world(
                payload, self.world, identity_mode="stat"
            )
        )
        self.assertIsNone(
            orientation.validate_orientation_for_world(
                payload, self.world, identity_mode="digest"
            )
        )

        self.alive.joinpath("_index.json").unlink()
        self.assertIsNone(
            orientation.validate_orientation_for_world(
                payload, self.world, identity_mode="stat"
            )
        )


if __name__ == "__main__":
    unittest.main()
