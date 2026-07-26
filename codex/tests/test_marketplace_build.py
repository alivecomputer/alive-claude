from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
BUILDER = PLUGIN_ROOT / "scripts" / "build_marketplace.py"


class MarketplaceBuildTests(unittest.TestCase):
    def build(self, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(BUILDER),
                "--plugin-root",
                str(PLUGIN_ROOT),
                "--output",
                str(output),
            ],
            text=True,
            capture_output=True,
            timeout=20,
        )

    def test_build_is_deterministic_and_contains_only_release_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first"
            second = Path(directory) / "second"
            first_result = self.build(first)
            self.assertEqual(0, first_result.returncode, first_result.stderr)
            second_result = self.build(second)
            self.assertEqual(0, second_result.returncode, second_result.stderr)

            catalog = json.loads(
                first.joinpath(".agents", "plugins", "marketplace.json").read_text()
            )
            self.assertEqual("alive-private-alpha", catalog["name"])
            self.assertEqual("alive", catalog["plugins"][0]["name"])
            self.assertEqual(
                "./plugins/alive", catalog["plugins"][0]["source"]["path"]
            )
            installed = first / "plugins" / "alive"
            self.assertTrue(installed.joinpath(".codex-plugin", "plugin.json").is_file())
            self.assertTrue(installed.joinpath("hooks", "hooks.json").is_file())
            self.assertTrue(installed.joinpath(".mcp.json").is_file())
            self.assertTrue(os.access(installed / "mcp" / "run.sh", os.X_OK))
            self.assertTrue(installed.joinpath("scripts", "e2e_codex_sessions.py").is_file())
            self.assertTrue(os.access(installed / "scripts" / "e2e_codex_sessions.sh", os.X_OK))
            for excluded in (
                ".venv",
                "tests",
                "docs-internal",
                "dist",
                "__pycache__",
                "node_modules",
            ):
                self.assertFalse(any(path.name == excluded for path in installed.rglob("*")))

            first_manifest = json.loads(first.joinpath("BUILD-MANIFEST.json").read_text())
            second_manifest = json.loads(second.joinpath("BUILD-MANIFEST.json").read_text())
            self.assertEqual(first_manifest, second_manifest)
            self.assertGreater(len(first_manifest["files"]), 20)


if __name__ == "__main__":
    unittest.main()
