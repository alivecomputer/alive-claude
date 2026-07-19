from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "alive"
HOOKS = PLUGIN / "hooks" / "scripts"


def make_world(base: Path) -> Path:
    world = base / "world"
    (world / ".alive" / "_squirrels").mkdir(parents=True)
    (world / ".alive" / "preferences.yaml").write_text(
        "github_star_ask: false\n", encoding="utf-8"
    )
    for domain in ("01_Archive", "02_Life", "03_Inbox", "04_Ventures", "05_Experiments"):
        (world / domain).mkdir()
    return world


def run_hook(script_name: str, world: Path, session_id: str, source: str) -> subprocess.CompletedProcess[str]:
    payload = {
        "session_id": session_id,
        "cwd": str(world),
        "hook_event_name": "SessionStart",
        "model": "test-model",
        "source": source,
        "transcript_path": str(world / "transcript.jsonl"),
    }
    env = os.environ.copy()
    env.update(
        {
            "ALIVE_WORLD_ROOT_OVERRIDE": str(world),
            "CLAUDE_PLUGIN_ROOT": str(PLUGIN),
            "CLAUDE_ENV_FILE": str(world / ".claude-env"),
        }
    )
    return subprocess.run(
        ["bash", str(HOOKS / script_name)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=world,
        env=env,
        timeout=30,
        check=False,
    )


class SessionHookRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base = Path(self.tempdir.name)
        self.world = make_world(self.base)

    def test_v3_life_kernel_and_generic_bundles_do_not_trigger_upgrade_warning(self) -> None:
        (self.world / "02_Life" / "_kernel").mkdir()
        (self.world / "02_Life" / "_kernel" / "key.md").write_text(
            "name: life\n", encoding="utf-8"
        )
        (self.world / "project" / "bundles" / "assets").mkdir(parents=True)

        result = run_hook("alive-session-new.sh", self.world, "session-start-safe", "startup")

        self.assertEqual(result.returncode, 0, result.stderr)
        json.loads(result.stdout)
        self.assertNotIn("YOUR WORLD NEEDS MIGRATION", result.stdout)

    def test_resume_recreates_exact_missing_session_instead_of_borrowing_active_entry(self) -> None:
        other = self.world / ".alive" / "_squirrels" / "other-active-session.yaml"
        other.write_text(
            "\n".join(
                [
                    "session_id: other-active-session",
                    "runtime_id: squirrel.core@1.0",
                    "engine: test-model",
                    "walnut: other-project",
                    "started: 2026-07-19T00:00:00",
                    "ended: null",
                    "saves: 0",
                    "stash: []",
                    "working: []",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        result = run_hook(
            "alive-session-resume.sh", self.world, "session-resume-missing", "resume"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        json.loads(result.stdout)
        entry = self.world / ".alive" / "_squirrels" / "session-resume-missing.yaml"
        self.assertTrue(entry.is_file())
        content = entry.read_text(encoding="utf-8")
        for expected in (
            "session_id: session-resume-missing",
            "ended: null",
            "saves: 0",
            "stash: []",
            "working: []",
        ):
            self.assertIn(expected, content)
        self.assertNotIn("other-active-session", result.stdout)


if __name__ == "__main__":
    unittest.main()
