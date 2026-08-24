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

    def assert_env_file_round_trips_world_path(
        self, script_name: str, source: str, session_id: str
    ) -> None:
        spaced_base = self.base / "parent with spaces and ' quote"
        spaced_base.mkdir()
        world = make_world(spaced_base)

        result = run_hook(script_name, world, session_id, source)

        self.assertEqual(result.returncode, 0, result.stderr)
        env_file = world / ".claude-env"
        self.assertTrue(env_file.is_file())
        shell_result = subprocess.run(
            [
                "zsh",
                "-c",
                'source "$1"; printf "%s\\n" "$ALIVE_WORLD_ROOT"',
                "zsh",
                str(env_file),
            ],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(shell_result.returncode, 0, shell_result.stderr)
        self.assertEqual(shell_result.stdout.strip(), str(world))

    def test_new_session_env_file_quotes_world_paths_with_spaces(self) -> None:
        self.assert_env_file_round_trips_world_path(
            "alive-session-new.sh", "startup", "session-spaced-new"
        )

    def test_resume_env_file_quotes_world_paths_with_spaces(self) -> None:
        self.assert_env_file_round_trips_world_path(
            "alive-session-resume.sh", "resume", "session-spaced-resume"
        )

    def test_new_session_refreshes_managed_agents_file_and_claude_bridge(self) -> None:
        managed = self.world / ".alive" / "agents.md"
        managed.write_text("legacy _core/ instructions\n", encoding="utf-8")
        claude_dir = self.world / ".claude"
        claude_dir.mkdir()
        bridge = claude_dir / "CLAUDE.md"
        bridge.write_text("legacy user-visible instructions\n", encoding="utf-8")

        result = run_hook(
            "alive-session-new.sh", self.world, "session-agent-refresh", "startup"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        template = (PLUGIN / "templates" / "world" / "agents.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(managed.read_text(encoding="utf-8"), template)
        self.assertEqual(bridge.read_text(encoding="utf-8"), template)
        self.assertTrue((claude_dir / "CLAUDE.md.pre-alive-3.2.1.bak").is_file())

    def test_new_session_injects_canonical_rule_overrides(self) -> None:
        (self.world / ".alive" / "overrides.md").write_text(
            "# Overrides\n\n- Always use midnight blue in examples.\n",
            encoding="utf-8",
        )

        result = run_hook(
            "alive-session-new.sh", self.world, "session-overrides", "startup"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Always use midnight blue in examples", result.stdout)

    def test_new_session_writes_valid_statusline_settings_json(self) -> None:
        result = run_hook(
            "alive-session-new.sh", self.world, "session-settings-json", "startup"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        settings = self.world / ".claude" / "settings.json"
        self.assertTrue(settings.is_file(), "SessionStart should create settings.json")
        data = json.loads(settings.read_text(encoding="utf-8"))
        command = data["statusLine"]["command"]
        self.assertTrue(command, "statusLine.command must not be empty")
        self.assertIn("statusline.sh", command)
        self.assertIn("bash ", command)

    def test_new_session_settings_json_survives_spaces_in_world_path(self) -> None:
        spaced_base = self.base / "parent with spaces"
        spaced_base.mkdir()
        world = make_world(spaced_base)

        result = run_hook(
            "alive-session-new.sh", world, "session-settings-spaced", "startup"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        settings = world / ".claude" / "settings.json"
        data = json.loads(settings.read_text(encoding="utf-8"))
        command = data["statusLine"]["command"]
        self.assertIn("parent with spaces", command)
        self.assertTrue(command.startswith("bash "))


if __name__ == "__main__":
    unittest.main()

