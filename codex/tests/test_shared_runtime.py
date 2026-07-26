from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
SYNC = PLUGIN_ROOT / "scripts" / "sync_shared_runtime.py"


class SharedRuntimeSyncTests(unittest.TestCase):
    def run_sync(
        self, source: Path, plugin: Path, manifest: Path, *, check: bool = False
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(SYNC),
            "--source-root",
            str(source),
            "--plugin-root",
            str(plugin),
            "--manifest",
            str(manifest),
        ]
        if check:
            command.append("--check")
        return subprocess.run(command, text=True, capture_output=True, timeout=5)

    def test_sync_copies_only_allowlisted_files_and_check_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            plugin = root / "plugin"
            source.joinpath("scripts").mkdir(parents=True)
            source.joinpath("templates", "walnut").mkdir(parents=True)
            source.joinpath("private.txt").write_text("secret", encoding="utf-8")
            source.joinpath("scripts", "project.py").write_text(
                "print('project')\n", encoding="utf-8"
            )
            source.joinpath("templates", "walnut", "key.md").write_text(
                "---\ntype: project\n---\n", encoding="utf-8"
            )
            manifest = root / "shared-runtime.json"
            manifest.write_text(
                json.dumps(
                    {
                        "files": ["scripts/project.py"],
                        "trees": ["templates"],
                    }
                ),
                encoding="utf-8",
            )

            copied = self.run_sync(source, plugin, manifest)
            self.assertEqual(0, copied.returncode, copied.stderr)
            self.assertTrue(plugin.joinpath("scripts", "project.py").is_file())
            self.assertTrue(plugin.joinpath("templates", "walnut", "key.md").is_file())
            self.assertFalse(plugin.joinpath("private.txt").exists())

            clean = self.run_sync(source, plugin, manifest, check=True)
            self.assertEqual(0, clean.returncode, clean.stdout + clean.stderr)
            self.assertEqual([], json.loads(clean.stdout)["divergent"])

            plugin.joinpath("scripts", "project.py").write_text(
                "print('drift')\n", encoding="utf-8"
            )
            drift = self.run_sync(source, plugin, manifest, check=True)
            self.assertEqual(1, drift.returncode)
            self.assertEqual(
                ["scripts/project.py"], json.loads(drift.stdout)["divergent"]
            )


if __name__ == "__main__":
    unittest.main()
