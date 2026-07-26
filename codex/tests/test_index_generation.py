from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


GENERATOR = Path(__file__).resolve().parents[2] / "plugins" / "alive" / "scripts" / "generate-index.py"


class IndexGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.world = Path(self.temporary_directory.name)
        self.world.joinpath(".alive", "_squirrels").mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def run_generator(
        self,
        *,
        extra_env: dict[str, str] | None = None,
        build_orientation: bool = False,
        generator: Path = GENERATOR,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment.update(extra_env or {})
        command = [sys.executable, str(generator), str(self.world)]
        if build_orientation:
            command.append("--build-orientation")
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            env=environment,
            timeout=10,
        )

    def write_squirrel(self, *, tags: list[str]) -> None:
        tags_text = "".join(f"  - {tag}\n" for tag in tags)
        self.world.joinpath(".alive", "_squirrels", "session.yaml").write_text(
            "session_id: session-123\n"
            "walnut: demo\n"
            "started: 2026-07-25T01:00:00Z\n"
            "saves: 2\n"
            "tags:\n"
            + tags_text,
            encoding="utf-8",
        )

    def test_multiline_squirrel_tags_are_preserved_without_leading_dash(self) -> None:
        squirrel = self.world / ".alive" / "_squirrels" / "session.yaml"
        squirrel.write_text(
            "session_id: session-123\n"
            "walnut: demo\n"
            "started: 2026-07-25T01:00:00Z\n"
            "saves: 2\n"
            "tags:\n"
            "  - supernormal-winddown\n"
            "  - patrick-super\n"
            "  - sgc\n",
            encoding="utf-8",
        )
        result = self.run_generator()
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads((self.world / ".alive" / "_index.json").read_text())
        self.assertEqual(
            ["supernormal-winddown", "patrick-super", "sgc"],
            payload["recent_sessions"][0]["tags"],
        )
        yaml_payload = json.loads(
            (self.world / ".alive" / "_index.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual(payload, yaml_payload)

    def test_generated_yaml_is_json_compatible_and_preserves_hostile_scalars(self) -> None:
        walnut = self.world / "04_Ventures" / "null: 2026-07-25 🚀"
        kernel = walnut / "_kernel"
        bundle = walnut / "true:bundle"
        kernel.mkdir(parents=True)
        bundle.mkdir()
        kernel.joinpath("key.md").write_text(
            "---\n"
            "type: null\n"
            "goal: \"yes: ship #1 🚀\"\n"
            "rhythm: 2026-07-25\n"
            "tags: [true, null, 001, needs:review, unicode-雪]\n"
            "people:\n"
            "  - name: false\n"
            "---\n",
            encoding="utf-8",
        )
        kernel.joinpath("now.json").write_text(
            json.dumps(
                {
                    "phase": "false",
                    "updated": "2026-07-25",
                    "bundle": "true:bundle",
                    "next": {"action": "null: next"},
                    "unscoped_tasks": {"counts": {"urgent": 1}},
                    "bundles": {"summary": {"draft": 1}},
                    "blockers": ["yes: blocked"],
                    "recent_sessions": [],
                    "children": {},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        bundle.joinpath("context.manifest.yaml").write_text(
            "goal: \"no: maybe\"\nstatus: null\nupdated: 2026-07-25\n",
            encoding="utf-8",
        )
        self.write_squirrel(
            tags=["needs:review", "-leading", 'quoted "value"', "true", "null", "雪"]
        )
        self.assertEqual(0, self.run_generator().returncode)
        yaml_text = (self.world / ".alive" / "_index.yaml").read_text(encoding="utf-8")
        yaml_payload = json.loads(yaml_text)
        json_payload = json.loads(
            (self.world / ".alive" / "_index.json").read_text(encoding="utf-8")
        )
        self.assertEqual(json_payload, yaml_payload)
        entry = next(item for item in json_payload["walnuts"] if item["name"].startswith("null:"))
        self.assertEqual("null", entry["type"])
        self.assertEqual("false", entry["phase"])
        self.assertEqual("2026-07-25", entry["rhythm"])
        self.assertEqual(["true", "null", "001", "needs:review", "unicode-雪"], entry["tags"])
        self.assertEqual(["false"], entry["people"])
        self.assertEqual("null", entry["capsules"][0]["status"])
        try:
            import yaml  # type: ignore
        except ImportError:
            pass
        else:
            self.assertEqual(json_payload, yaml.safe_load(yaml_text))

    def test_shared_generator_does_not_refresh_orientation_without_codex_flag(self) -> None:
        """The unchanged Claude post-write invocation must not opt into Codex orientation."""
        result = self.run_generator()
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse((self.world / ".alive" / "_orientation.json").exists())

        codex_result = self.run_generator(build_orientation=True)
        self.assertEqual(0, codex_result.returncode, codex_result.stderr)
        orientation = json.loads(
            (self.world / ".alive" / "_orientation.json").read_text()
        )
        self.assertEqual(1, orientation["schema_version"])
        self.assertTrue(orientation["health"]["index_valid"])

    def test_world_local_generator_runs_without_orientation_module(self) -> None:
        """Graph setup copies only generate-index.py, so its default path must be standalone."""
        copied = self.world / ".alive" / "scripts" / "generate-index.py"
        copied.parent.mkdir(parents=True)
        shutil.copyfile(GENERATOR, copied)
        result = self.run_generator(generator=copied)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(self.world.joinpath(".alive", "_index.json").is_file())
        self.assertFalse(self.world.joinpath(".alive", "_orientation.json").exists())

    def test_failed_generation_preserves_previous_indexes(self) -> None:
        alive = self.world / ".alive"
        alive.joinpath("_index.json").write_text('{"sentinel": true}\n')
        alive.joinpath("_index.yaml").write_text("sentinel: true\n")
        result = self.run_generator(extra_env={"ALIVE_INDEX_TEST_FAIL": "1"})
        self.assertNotEqual(0, result.returncode)
        self.assertEqual('{"sentinel": true}\n', alive.joinpath("_index.json").read_text())
        self.assertEqual("sentinel: true\n", alive.joinpath("_index.yaml").read_text())

    def test_second_replace_failure_rolls_back_the_index_pair(self) -> None:
        """A failure after replacing the first file must not expose mixed generations."""
        alive = self.world / ".alive"
        alive.joinpath("_index.json").write_text(
            '{"generation":"old","sentinel":true}\n', encoding="utf-8"
        )
        alive.joinpath("_index.yaml").write_text(
            '{"generation":"old","sentinel":true}\n', encoding="utf-8"
        )
        result = self.run_generator(
            extra_env={"ALIVE_INDEX_TEST_FAIL_SECOND_REPLACE": "1"}
        )
        self.assertNotEqual(0, result.returncode)
        self.assertEqual(
            {"generation": "old", "sentinel": True},
            json.loads(alive.joinpath("_index.json").read_text(encoding="utf-8")),
        )
        self.assertEqual(
            {"generation": "old", "sentinel": True},
            json.loads(alive.joinpath("_index.yaml").read_text(encoding="utf-8")),
        )

    def test_successful_index_pair_has_one_generation_marker(self) -> None:
        result = self.run_generator()
        self.assertEqual(0, result.returncode, result.stderr)
        json_payload = json.loads(
            self.world.joinpath(".alive", "_index.json").read_text(encoding="utf-8")
        )
        yaml_payload = json.loads(
            self.world.joinpath(".alive", "_index.yaml").read_text(encoding="utf-8")
        )
        self.assertRegex(json_payload["generation"], r"^[a-f0-9]{32}$")
        self.assertEqual(json_payload["generation"], yaml_payload["generation"])
        self.assertEqual(json_payload, yaml_payload)


if __name__ == "__main__":
    unittest.main()
