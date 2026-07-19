from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_VERSION = "3.2.1"
EXPECTED_HOOK_COMMANDS = 14
EXPECTED_HOOK_EVENTS = 5


def command_scripts(node: object) -> list[str]:
    scripts: list[str] = []
    if isinstance(node, dict):
        if node.get("type") == "command" and isinstance(node.get("command"), str):
            match = re.search(r"hooks/scripts/([^\s]+\.sh)", node["command"])
            if match:
                scripts.append(match.group(1))
        for value in node.values():
            scripts.extend(command_scripts(value))
    elif isinstance(node, list):
        for value in node:
            scripts.extend(command_scripts(value))
    return scripts


class ReleaseMetadataContractTest(unittest.TestCase):
    def test_all_public_product_versions_are_3_2_1(self) -> None:
        marketplace = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
        plugin = json.loads(
            (ROOT / "plugins" / "alive" / ".claude-plugin" / "plugin.json").read_text()
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        claude = (ROOT / "plugins" / "alive" / "CLAUDE.md").read_text(encoding="utf-8")
        walnut = (ROOT / "walnut.manifest.yaml").read_text(encoding="utf-8")

        self.assertEqual(marketplace["metadata"]["version"], EXPECTED_VERSION)
        self.assertEqual(marketplace["plugins"][0]["version"], EXPECTED_VERSION)
        self.assertEqual(plugin["version"], EXPECTED_VERSION)
        self.assertIn(f"version-{EXPECTED_VERSION}-F97316", readme)
        self.assertRegex(claude, rf"(?m)^version: {re.escape(EXPECTED_VERSION)}$")
        self.assertRegex(walnut, rf'(?m)^version: "{re.escape(EXPECTED_VERSION)}"$')

    def test_world_schema_target_remains_3_2_0(self) -> None:
        source = (
            ROOT / "plugins" / "alive" / "scripts" / "system_upgrade" / "__init__.py"
        ).read_text(encoding="utf-8")
        self.assertIn('TARGET_WORLD_VERSION: str = "3.2.0"', source)

    def test_permission_contract_matches_declared_hook_surface(self) -> None:
        hooks = json.loads(
            (ROOT / "plugins" / "alive" / "hooks" / "hooks.json").read_text()
        )
        scripts = command_scripts(hooks)
        self.assertEqual(len(hooks["hooks"]), EXPECTED_HOOK_EVENTS)
        self.assertEqual(len(scripts), EXPECTED_HOOK_COMMANDS)

        permissions_path = ROOT / "PERMISSIONS.md"
        self.assertTrue(permissions_path.is_file(), "PERMISSIONS.md must exist")
        permissions = permissions_path.read_text(encoding="utf-8")
        self.assertIn(
            f"{EXPECTED_HOOK_COMMANDS} command invocations across "
            f"{EXPECTED_HOOK_EVENTS} Claude Code hook event types",
            permissions,
        )
        for script in sorted(set(scripts)):
            self.assertIn(script, permissions)


if __name__ == "__main__":
    unittest.main()
