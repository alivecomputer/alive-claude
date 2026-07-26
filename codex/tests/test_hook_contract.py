from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
HOOKS_PATH = PLUGIN_ROOT / "hooks" / "hooks.json"


class HookContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(HOOKS_PATH.read_text(encoding="utf-8"))
        cls.hooks = cls.payload["hooks"]

    def test_current_lifecycle_events_are_declared(self) -> None:
        self.assertTrue(
            {
                "SessionStart",
                "PreToolUse",
                "PostToolUse",
                "PreCompact",
                "PostCompact",
                "UserPromptSubmit",
                "Stop",
            }.issubset(self.hooks)
        )

    def test_session_start_covers_every_documented_source(self) -> None:
        matchers = "|".join(
            group.get("matcher", "") for group in self.hooks["SessionStart"]
        )
        for source in ("startup", "resume", "clear", "compact"):
            self.assertIsNotNone(re.fullmatch(matchers, source), source)

    def test_tool_matchers_cover_shell_and_write_aliases(self) -> None:
        for event in ("PreToolUse", "PostToolUse"):
            matchers = "|".join(
                group.get("matcher", "") for group in self.hooks[event]
            )
            for tool in (
                "Bash",
                "exec_command",
                "apply_patch",
                "functions.exec_command",
                "functions.apply_patch",
                "Edit",
                "Write",
            ):
                self.assertIsNotNone(re.fullmatch(matchers, tool), (event, tool))

    def test_unmatchable_events_do_not_declare_matchers(self) -> None:
        for event in ("UserPromptSubmit", "Stop"):
            for group in self.hooks[event]:
                self.assertNotIn("matcher", group)

    def test_every_command_resolves_inside_plugin_root(self) -> None:
        commands: list[str] = []
        for groups in self.hooks.values():
            for group in groups:
                for hook in group["hooks"]:
                    command = hook["command"]
                    commands.append(command)
                    self.assertIn("$PLUGIN_ROOT/hooks/scripts/", command)
                    self.assertNotIn("CODEX_PLUGIN_ROOT", command)
                    relative = command.split("$PLUGIN_ROOT/", 1)[1].split('"', 1)[0]
                    self.assertTrue((PLUGIN_ROOT / relative).is_file(), relative)
        self.assertGreater(len(commands), 10)

    def test_context_watch_does_not_read_full_index_files(self) -> None:
        text = (PLUGIN_ROOT / "hooks" / "scripts" / "alive-context-watch.sh").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("_index.yaml", text)
        self.assertNotIn("_index.json", text)


if __name__ == "__main__":
    unittest.main()
