from __future__ import annotations

import json
import hashlib
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOKS = PLUGIN_ROOT / "hooks" / "scripts"


def make_world(root: Path) -> tuple[Path, Path]:
    world = root / "World With Spaces"
    walnut = world / "04_Ventures" / "demo-walnut"
    for path in (
        world / "01_Archive",
        world / "02_Life",
        world / "03_Inbox",
        walnut / "_kernel",
        world / ".alive" / "_squirrels",
    ):
        path.mkdir(parents=True, exist_ok=True)
    world.joinpath(".alive", "key.md").write_text(
        "---\nname: Test Human\n---\n", encoding="utf-8"
    )
    walnut.joinpath("_kernel", "key.md").write_text(
        "---\ntype: venture\ngoal: Test recovery\ncreated: 2026-07-21\n---\n",
        encoding="utf-8",
    )
    walnut.joinpath("_kernel", "log.md").write_text(
        "---\ntype: log\n---\n\n## Initial\n", encoding="utf-8"
    )
    walnut.joinpath("_kernel", "insights.md").write_text(
        "---\ntype: insights\n---\n", encoding="utf-8"
    )
    walnut.joinpath("_kernel", "tasks.json").write_text(
        '{"tasks": []}\n', encoding="utf-8"
    )
    walnut.joinpath("_kernel", "completed.json").write_text(
        '{"completed": []}\n', encoding="utf-8"
    )
    return world, walnut


class HookRuntimeTests(unittest.TestCase):
    def write_orientation(
        self,
        world: Path,
        *,
        issue_count: int = 9,
        summary: str = "Review the launch plan",
    ) -> None:
        alive = world / ".alive"
        index_payload = {
            "generated": "2026-07-25T12:00:00Z",
            "generation": "0123456789abcdef0123456789abcdef",
            "stats": {"walnuts": 1, "people": 0, "inputs": 0},
            "walnuts": [
                {
                    "name": "demo-walnut",
                    "path": "04_Ventures/demo-walnut",
                }
            ],
            "people": [],
            "recent_sessions": [],
        }
        index_bytes = json.dumps(
            index_payload, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        alive.joinpath("_index.json").write_bytes(index_bytes)
        alive.joinpath("_index.yaml").write_bytes(index_bytes)
        index_stat = alive.joinpath("_index.json").stat()
        world.joinpath(".alive", "_orientation.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "generated": datetime.now(timezone.utc)
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z"),
                    "source_index": {
                        "generated": index_payload["generated"],
                        "generation": index_payload["generation"],
                        "digest": hashlib.sha256(index_bytes).hexdigest(),
                        "size": index_stat.st_size,
                        "mtime_ns": index_stat.st_mtime_ns,
                    },
                    "world": {
                        "root": str(world.resolve()),
                        "walnuts": 1,
                        "people": 0,
                        "unrouted_inputs": 0,
                    },
                    "health": {
                        "index_valid": True,
                        "projection_stale": False,
                        "issue_count": issue_count,
                        "malformed_source_count": 0,
                    },
                    "counts": {
                        "total_detected": issue_count,
                        "shown": 1,
                        "malformed_sources": 0,
                    },
                    "recommendations": [
                        {
                            "id": "task:demo-walnut:t001:overdue",
                            "kind": "overdue",
                            "severity": "critical",
                            "confidence": "high",
                            "walnut": "demo-walnut",
                            "task_id": "t001",
                            "summary": summary,
                            "evidence": {
                                "path": "04_Ventures/demo-walnut/_kernel/tasks.json",
                                "created": "2026-07-01",
                                "status": "active",
                            },
                            "proposed_action": "review_task",
                            "can_run_now": False,
                        }
                    ],
                }
            , ensure_ascii=False),
            encoding="utf-8",
        )

    def run_hook(
        self,
        name: str,
        payload: dict[str, object] | str,
        *,
        world: Path,
        home: Path,
        plugin_data: Path,
    ) -> subprocess.CompletedProcess[str]:
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        env = os.environ.copy()
        env.update(
            {
                "HOME": str(home),
                "PLUGIN_ROOT": str(PLUGIN_ROOT),
                "PLUGIN_DATA": str(plugin_data),
                "ALIVE_WORLD_ROOT": str(world),
            }
        )
        return subprocess.run(
            ["bash", str(HOOKS / name)],
            input=raw,
            text=True,
            capture_output=True,
            cwd=world,
            env=env,
            timeout=5,
        )

    def assert_orientation_health_notice(
        self, world: Path, root: Path, expected: str
    ) -> None:
        orientation = world / ".alive" / "_orientation.json"
        before = orientation.read_bytes() if orientation.is_file() else None
        before_mtime = orientation.stat().st_mtime_ns if orientation.is_file() else None
        for name in ("alive-session-start.sh", "alive-session-resume.sh"):
            with self.subTest(hook=name):
                result = self.run_hook(
                    name,
                    {
                        "session_id": f"session-health-{name}",
                        "cwd": str(world),
                        "hook_event_name": "SessionStart",
                        "source": "startup",
                    },
                    world=world,
                    home=root / f"home-{name}",
                    plugin_data=root / f"plugin-data-{name}",
                )
                self.assertEqual(0, result.returncode, result.stderr)
                context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
                self.assertIn(expected, context)
                self.assertLessEqual(len(context.encode()), 8192)
        if before is None:
            self.assertFalse(orientation.exists())
        else:
            self.assertEqual(before, orientation.read_bytes())
            self.assertEqual(before_mtime, orientation.stat().st_mtime_ns)

    def test_session_start_is_codex_native_and_creates_v33_entry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            result = self.run_hook(
                "alive-session-start.sh",
                {
                    "session_id": "session-one",
                    "cwd": str(world),
                    "hook_event_name": "SessionStart",
                    "source": "startup",
                    "model": "gpt-test",
                    "transcript_path": str(root / "session-one.jsonl"),
                },
                world=world,
                home=root / "home",
                plugin_data=root / "plugin-data",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(
                "SessionStart", output["hookSpecificOutput"]["hookEventName"]
            )
            self.assertIn("World With Spaces", output["hookSpecificOutput"]["additionalContext"])
            entry = world / ".alive" / "_squirrels" / "session-one.yaml"
            self.assertIn("runtime_id: squirrel.core@3.3", entry.read_text())
            self.assertFalse(world.joinpath(".claude").exists())

    def test_session_start_injects_bounded_orientation_not_full_index(self) -> None:
        """Skipping cached rendering would hide actionable orientation at startup."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            self.write_orientation(world)
            world.joinpath(".alive", "_index.yaml").write_text(
                "SECRET_FULL_INDEX", encoding="utf-8"
            )
            result = self.run_hook(
                "alive-session-start.sh",
                {
                    "session_id": "session-orientation",
                    "cwd": str(world),
                    "hook_event_name": "SessionStart",
                    "source": "startup",
                },
                world=world,
                home=root / "home",
                plugin_data=root / "plugin-data",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("ALIVE found 9 things needing attention.", context)
            self.assertNotIn("SECRET_FULL_INDEX", context)
            self.assertLessEqual(len(context.encode()), 8192)

    def test_missing_orientation_is_nonfatal(self) -> None:
        """A missing cache must be surfaced without trying to build one."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            self.assert_orientation_health_notice(
                world, root, "ALIVE orientation cache is missing."
            )

    def test_malformed_orientation_is_reported_without_startup_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            world.joinpath(".alive", "_orientation.json").write_text(
                "{not json", encoding="utf-8"
            )
            self.assert_orientation_health_notice(
                world, root, "ALIVE orientation cache is invalid."
            )

    def test_unsupported_orientation_schema_is_reported_without_startup_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            world.joinpath(".alive", "_orientation.json").write_text(
                '{"schema_version":2,"health":{},"counts":{},"recommendations":[]}',
                encoding="utf-8",
            )
            self.assert_orientation_health_notice(
                world, root, "ALIVE orientation cache has an unsupported schema."
            )

    def test_stale_orientation_is_reported_without_startup_regeneration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            self.write_orientation(world)
            orientation = world / ".alive" / "_orientation.json"
            index = world / ".alive" / "_index.json"
            index.write_text("{}", encoding="utf-8")
            os.utime(orientation, (1, 1))
            os.utime(index, (2, 2))
            self.assert_orientation_health_notice(
                world, root, "ALIVE orientation cache is stale."
            )

    def test_orientation_with_missing_source_index_is_unverifiable_at_startup(self) -> None:
        """A cache cannot be trusted when its bound index has disappeared."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            self.write_orientation(world)
            world.joinpath(".alive", "_index.json").unlink()
            world.joinpath(".alive", "_index.yaml").unlink()
            self.assert_orientation_health_notice(
                world, root, "ALIVE orientation source index is missing."
            )

    def test_session_resume_injects_cached_bounded_orientation(self) -> None:
        """Dropping cached rendering would hide recommendations after compaction."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root)
            self.write_orientation(world)
            world.joinpath(".alive", "_squirrels", "session-resume.yaml").write_text(
                "session_id: session-resume\n"
                "runtime_id: squirrel.core@3.3\n"
                f"walnut: {walnut}\n"
                "ended: null\n"
                "saves: 1\n"
                "recovery_state: Resume the launch.\n",
                encoding="utf-8",
            )
            result = self.run_hook(
                "alive-session-resume.sh",
                {
                    "session_id": "session-resume",
                    "cwd": str(world),
                    "hook_event_name": "SessionStart",
                    "source": "compact",
                },
                world=world,
                home=root / "home",
                plugin_data=root / "plugin-data",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn("ALIVE found 9 things needing attention.", context)
            self.assertLessEqual(len(context.encode()), 8192)

    def test_session_resume_caps_oversized_recovery_without_losing_orientation(self) -> None:
        """An oversized saved state must not push additionalContext past Codex's byte limit."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root)
            self.write_orientation(world)
            world.joinpath(".alive", "_squirrels", "session-large-resume.yaml").write_text(
                "session_id: session-large-resume\n"
                "runtime_id: squirrel.core@3.3\n"
                f"walnut: {walnut}\n"
                "ended: null\n"
                "saves: 1\n"
                f"recovery_state: {'💡' * 3000}\n",
                encoding="utf-8",
            )
            result = self.run_hook(
                "alive-session-resume.sh",
                {
                    "session_id": "session-large-resume",
                    "cwd": str(world),
                    "hook_event_name": "SessionStart",
                    "source": "compact",
                },
                world=world,
                home=root / "home",
                plugin_data=root / "plugin-data",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertLessEqual(len(context.encode()), 8192)
            self.assertNotIn("\ufffd", context)
            self.assertIn("Recovery state: 💡", context)
            self.assertIn("ALIVE found 9 things needing attention.", context)

    def test_repeated_session_start_caps_oversized_recovery_with_orientation(self) -> None:
        """The startup-to-resume path must keep recovery and cached orientation in budget."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root)
            self.write_orientation(world)
            world.joinpath(".alive", "_squirrels", "session-large-start.yaml").write_text(
                "session_id: session-large-start\n"
                "runtime_id: squirrel.core@3.3\n"
                f"walnut: {walnut}\n"
                "ended: null\n"
                "saves: 1\n"
                f"recovery_state: {'💡' * 3000}\n",
                encoding="utf-8",
            )
            result = self.run_hook(
                "alive-session-start.sh",
                {
                    "session_id": "session-large-start",
                    "cwd": str(world),
                    "hook_event_name": "SessionStart",
                    "source": "startup",
                },
                world=world,
                home=root / "home",
                plugin_data=root / "plugin-data",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertLessEqual(len(context.encode()), 8192)
            self.assertNotIn("\ufffd", context)
            self.assertIn("Recovery state: 💡", context)
            self.assertIn("ALIVE found 9 things needing attention.", context)

    def test_resume_clips_recovery_larger_than_the_os_environment_limit(self) -> None:
        """Recovery must stream into the clipper rather than becoming an exec environment."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root)
            self.write_orientation(world)
            world.joinpath(".alive", "_squirrels", "session-huge-resume.yaml").write_text(
                "session_id: session-huge-resume\n"
                "runtime_id: squirrel.core@3.3\n"
                f"walnut: {walnut}\n"
                "ended: null\n"
                "saves: 1\n"
                f"recovery_state: {'💡' * 700000}\n",
                encoding="utf-8",
            )
            result = self.run_hook(
                "alive-session-resume.sh",
                {
                    "session_id": "session-huge-resume",
                    "cwd": str(world),
                    "hook_event_name": "SessionStart",
                    "source": "compact",
                },
                world=world,
                home=root / "home",
                plugin_data=root / "plugin-data",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertLessEqual(len(context.encode()), 8192)
            self.assertNotIn("\ufffd", context)
            self.assertIn("ALIVE found 9 things needing attention.", context)

    def test_repeated_session_start_preserves_loaded_walnut_and_saves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root)
            plugin_data = root / "plugin-data"
            payload = {
                "session_id": "session-repeat",
                "cwd": str(world),
                "hook_event_name": "SessionStart",
                "source": "startup",
                "model": "gpt-test",
                "transcript_path": str(root / "session-repeat.jsonl"),
            }
            first = self.run_hook(
                "alive-session-start.sh",
                payload,
                world=world,
                home=root / "home",
                plugin_data=plugin_data,
            )
            self.assertEqual(0, first.returncode, first.stderr)
            entry = world / ".alive" / "_squirrels" / "session-repeat.yaml"
            entry.write_text(
                "session_id: session-repeat\n"
                "runtime_id: squirrel.core@3.3\n"
                f"walnut: {walnut}\n"
                "ended: null\n"
                "saves: 3\n"
                "recovery_state: Continue the beta release.\n",
                encoding="utf-8",
            )

            repeated = self.run_hook(
                "alive-session-start.sh",
                payload,
                world=world,
                home=root / "home",
                plugin_data=plugin_data,
            )
            self.assertEqual(0, repeated.returncode, repeated.stderr)
            preserved = entry.read_text(encoding="utf-8")
            self.assertIn(f"walnut: {walnut}", preserved)
            self.assertIn("saves: 3", preserved)
            self.assertIn("Continue the beta release.", preserved)

    def test_stop_updates_entry_and_writes_plugin_recovery_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root)
            entry = world / ".alive" / "_squirrels" / "session-stop.yaml"
            entry.write_text(
                "session_id: session-stop\n"
                "runtime_id: squirrel.core@3.3\n"
                f"walnut: {walnut}\n"
                "ended: null\n"
                "saves: 1\n"
                "recovery_state: Continue the private alpha.\n",
                encoding="utf-8",
            )
            plugin_data = root / "plugin-data"
            result = self.run_hook(
                "alive-stop.sh",
                {
                    "session_id": "session-stop",
                    "cwd": str(world),
                    "hook_event_name": "Stop",
                },
                world=world,
                home=root / "home",
                plugin_data=plugin_data,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertNotIn("ended: null", entry.read_text())
            recovery = json.loads(
                plugin_data.joinpath("recovery", "session-stop.json").read_text()
            )
            self.assertEqual(str(walnut), recovery["walnut"])
            self.assertEqual("Continue the private alpha.", recovery["recovery_state"])

    def test_compaction_round_trip_restores_orientation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root)
            world.joinpath(".alive", "_squirrels", "session-compact.yaml").write_text(
                "session_id: session-compact\n"
                "runtime_id: squirrel.core@3.3\n"
                f"walnut: {walnut}\n"
                "ended: null\n"
                "saves: 2\n"
                "recovery_state: Re-open the launch bundle.\n",
                encoding="utf-8",
            )
            plugin_data = root / "plugin-data"
            base = {
                "session_id": "session-compact",
                "cwd": str(world),
                "trigger": "auto",
            }
            before = self.run_hook(
                "alive-pre-compact.sh",
                base | {"hook_event_name": "PreCompact"},
                world=world,
                home=root / "home",
                plugin_data=plugin_data,
            )
            self.assertEqual(0, before.returncode, before.stderr)
            self.assertTrue(
                plugin_data.joinpath("recovery", "session-compact.json").is_file()
            )
            after = self.run_hook(
                "alive-post-compact.sh",
                base | {"hook_event_name": "PostCompact"},
                world=world,
                home=root / "home",
                plugin_data=plugin_data,
            )
            self.assertEqual(0, after.returncode, after.stderr)
            self.assertEqual("", after.stdout)
            resumed = self.run_hook(
                "alive-session-resume.sh",
                base
                | {
                    "hook_event_name": "SessionStart",
                    "source": "compact",
                    "model": "gpt-test",
                },
                world=world,
                home=root / "home",
                plugin_data=plugin_data,
            )
            self.assertEqual(0, resumed.returncode, resumed.stderr)
            context = json.loads(resumed.stdout)["hookSpecificOutput"]["additionalContext"]
            self.assertIn(str(walnut), context)
            self.assertIn("Re-open the launch bundle.", context)

    def test_post_write_projects_log_synchronously(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root)
            result = self.run_hook(
                "alive-post-write.sh",
                {
                    "session_id": "session-write",
                    "cwd": str(world),
                    "hook_event_name": "PostToolUse",
                    "tool_name": "apply_patch",
                    "tool_input": {
                        "changes": {
                            str(walnut / "_kernel" / "log.md"): {"update": "entry"}
                        }
                    },
                },
                world=world,
                home=root / "home",
                plugin_data=root / "plugin-data",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue(walnut.joinpath("_kernel", "now.json").is_file())
            self.assertTrue(world.joinpath(".alive", "_index.json").is_file())
            self.assertTrue(world.joinpath(".alive", "_orientation.json").is_file())

    def test_malformed_input_is_a_quiet_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            result = self.run_hook(
                "alive-stop.sh",
                "not-json",
                world=world,
                home=root / "home",
                plugin_data=root / "plugin-data",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("", result.stdout)

    def test_context_watch_uses_only_bounded_orientation_or_health(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            alive = world / ".alive"
            alive.joinpath("key.md").write_text("K" * 20000, encoding="utf-8")
            alive.joinpath("_index.yaml").write_text(
                "FULL_INDEX_SENTINEL_YAML" * 5000, encoding="utf-8"
            )
            alive.joinpath("_index.json").write_text(
                json.dumps({"sentinel": "FULL_INDEX_SENTINEL_JSON" * 5000}),
                encoding="utf-8",
            )
            alive.joinpath("_squirrels", "other.yaml").write_text(
                "session_id: other\nended: null\nsaves: 0\nwalnut: demo-walnut\n"
                f"stash:\n  - content: {'S' * 20000}\n",
                encoding="utf-8",
            )

            cases = {
                "valid": (lambda: self.write_orientation(world), "ALIVE found 9 things"),
                "missing": (lambda: None, "ALIVE orientation cache is missing."),
                "malformed": (
                    lambda: alive.joinpath("_orientation.json").write_text("{bad", encoding="utf-8"),
                    "ALIVE orientation cache is invalid.",
                ),
                "oversized": (
                    lambda: alive.joinpath("_orientation.json").write_bytes(b"{" + b" " * 8192 + b"}"),
                    "ALIVE orientation cache is invalid.",
                ),
                "stale": (lambda: self.write_orientation(world), "ALIVE orientation cache is stale."),
            }
            for name, (prepare, expected) in cases.items():
                with self.subTest(cache=name):
                    orientation = alive / "_orientation.json"
                    orientation.unlink(missing_ok=True)
                    prepare()
                    if name == "stale":
                        os.utime(orientation, (1, 1))
                        os.utime(alive / "_index.json", (2, 2))
                    alive.joinpath(".context_pct").write_text("80", encoding="utf-8")
                    session = f"watch-{name}-{root.name}-{'x' * 400}"
                    result = self.run_hook(
                        "alive-context-watch.sh",
                        {
                            "session_id": session,
                            "cwd": str(world),
                            "hook_event_name": "UserPromptSubmit",
                        },
                        world=world,
                        home=root / f"home-{name}",
                        plugin_data=root / f"plugin-data-{name}",
                    )
                    self.assertEqual(0, result.returncode, result.stderr)
                    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
                    self.assertIn(expected, context)
                    self.assertNotIn("FULL_INDEX_SENTINEL", context)
                    self.assertLessEqual(len(context.encode()), 8192)

    def test_context_watch_emits_json_for_all_orientation_control_characters(self) -> None:
        """Removing standards-compliant JSON encoding would corrupt valid hook output."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, _ = make_world(root)
            summary = "Review 🧭\bthe\flaunch café"
            self.write_orientation(world, summary=summary)
            world.joinpath(".alive", ".context_pct").write_text("80", encoding="utf-8")
            result = self.run_hook(
                "alive-context-watch.sh",
                {
                    "session_id": f"watch-controls-{root.name}",
                    "cwd": str(world),
                    "hook_event_name": "UserPromptSubmit",
                },
                world=world,
                home=root / "home",
                plugin_data=root / "plugin-data",
            )
            self.assertEqual(0, result.returncode, result.stderr)
            output = json.loads(result.stdout)
            context = output["hookSpecificOutput"]["additionalContext"]
            self.assertIn(summary, context)
            self.assertLessEqual(len(context.encode()), 8192)


if __name__ == "__main__":
    unittest.main()
