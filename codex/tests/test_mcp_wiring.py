from __future__ import annotations

import json
import ast
import re
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
MCP_ROOT = PLUGIN_ROOT / "mcp"


class McpWiringTests(unittest.TestCase):
    def test_plugin_launches_only_the_packaged_mcp_wrapper(self) -> None:
        config = json.loads(PLUGIN_ROOT.joinpath(".mcp.json").read_text())
        server = config["mcpServers"]["alive"]
        self.assertEqual("bash", server["command"])
        self.assertEqual(["${PLUGIN_ROOT}/mcp/run.sh"], server["args"])
        wrapper = MCP_ROOT.joinpath("run.sh").read_text()
        self.assertNotIn("uvx", wrapper)
        self.assertNotRegex(wrapper, r"https?://")
        self.assertIn("mcp/.venv/bin/python", wrapper)
        self.assertIn("PYTHONPATH", wrapper)
        self.assertIn("mcp/src", wrapper)

    def test_recovered_server_is_versioned_and_read_only(self) -> None:
        pyproject_path = MCP_ROOT / "pyproject.toml"
        self.assertTrue(pyproject_path.is_file(), "packaged MCP pyproject is missing")
        pyproject = pyproject_path.read_text(encoding="utf-8")
        self.assertIn('version = "3.3.0"', pyproject)
        self.assertIn("Read-only Model Context Protocol server", pyproject)
        snapshot = json.loads(
            MCP_ROOT.joinpath(
                "tests", "fixtures", "contracts", "tools.snapshot.json"
            ).read_text(encoding="utf-8")
        )
        tools = snapshot["tools"] if isinstance(snapshot, dict) else snapshot
        names = [tool["name"] for tool in tools]
        self.assertEqual(12, len(names))
        forbidden = re.compile(
            r"(?:^|_)(?:add|create|delete|done|edit|publish|remove|save|set|update|write)(?:_|$)"
        )
        self.assertEqual([], [name for name in names if forbidden.search(name)])
        for tool in tools:
            annotations = tool.get("annotations", {})
            self.assertIs(True, annotations.get("readOnlyHint"), tool["name"])
            self.assertIs(False, annotations.get("destructiveHint"), tool["name"])
            self.assertIs(False, annotations.get("openWorldHint"), tool["name"])

    def test_mcp_source_contains_no_outbound_network_clients(self) -> None:
        network_modules = {"aiohttp", "httpx", "requests", "socket", "urllib.request"}
        offenders = []
        for source in MCP_ROOT.joinpath("src").rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            if any(
                module == blocked or module.startswith(blocked + ".")
                for module in imported
                for blocked in network_modules
            ):
                offenders.append(source.relative_to(MCP_ROOT).as_posix())
        self.assertEqual([], offenders)

    def test_locked_test_environment_declares_its_runner(self) -> None:
        pyproject = MCP_ROOT.joinpath("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[dependency-groups]", pyproject)
        self.assertRegex(pyproject, r'test\s*=\s*\[\s*"pytest>=')

    def test_contract_snapshot_runner_never_fetches_dependencies(self) -> None:
        runner = MCP_ROOT.joinpath(
            "scripts", "run-inspector-snapshot.sh"
        ).read_text(encoding="utf-8")
        self.assertNotRegex(runner, r"\bnpx\s+(?:-y|--yes)\b")
        self.assertNotIn("uv run", runner)
        self.assertIn("node_modules/.bin/mcp-inspector", runner)
        self.assertIn("run.sh", runner)
        self.assertIn("npm ci", runner)

    def test_installer_prepares_dependencies_without_editable_project(self) -> None:
        installer_library = PLUGIN_ROOT.joinpath(
            "lib", "codex-plugin.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("--no-install-project", installer_library)
        doctor = PLUGIN_ROOT.joinpath("doctor.sh").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH", doctor)


if __name__ == "__main__":
    unittest.main()
