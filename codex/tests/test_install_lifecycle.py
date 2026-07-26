from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_hook_runtime import make_world


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CODEX_BIN = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
BUILDER = PLUGIN_ROOT / "scripts" / "build_marketplace.py"


class InstallLifecycleTests(unittest.TestCase):
    def run_script(
        self, name: str, *, codex_home: Path, marketplace: Path, extra: list[str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CODEX_HOME"] = str(codex_home)
        command = [
            "bash",
            str(PLUGIN_ROOT / name),
            "--codex-bin",
            str(CODEX_BIN),
            "--codex-home",
            str(codex_home),
            "--marketplace",
            str(marketplace),
            "--skip-mcp-setup",
            "--json",
        ]
        command.extend(extra or [])
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            env=env,
            timeout=30,
        )

    def test_install_reinstall_upgrade_and_uninstall_preserve_user_state(self) -> None:
        self.assertTrue(CODEX_BIN.is_file())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marketplace = root / "marketplace"
            build = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--plugin-root",
                    str(PLUGIN_ROOT),
                    "--output",
                    str(marketplace),
                ],
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(0, build.returncode, build.stderr)
            codex_home = root / "codex-home"
            codex_home.mkdir()
            sentinel_config = 'model = "gpt-test"\ncustom_sentinel = "keep-me"\n'
            codex_home.joinpath("config.toml").write_text(
                sentinel_config, encoding="utf-8"
            )
            world = root / "world"
            world.mkdir()
            world.joinpath("KEEP.txt").write_text("user world", encoding="utf-8")

            installed = self.run_script(
                "install.sh", codex_home=codex_home, marketplace=marketplace
            )
            self.assertEqual(0, installed.returncode, installed.stderr)
            evidence = json.loads(installed.stdout)
            self.assertEqual("installed", evidence["status"])
            cache_root = Path(evidence["plugin_root"])
            self.assertTrue(cache_root.joinpath(".codex-plugin", "plugin.json").is_file())
            self.assertTrue(cache_root.joinpath("hooks", "hooks.json").is_file())
            self.assertTrue(cache_root.joinpath("mcp", "pyproject.toml").is_file())
            self.assertNotIn("hooks.json", codex_home.joinpath("config.toml").read_text())

            diagnosed = self.run_script(
                "doctor.sh", codex_home=codex_home, marketplace=marketplace
            )
            self.assertEqual(0, diagnosed.returncode, diagnosed.stderr)
            diagnosis = json.loads(diagnosed.stdout)
            self.assertEqual("warn", diagnosis["status"])
            checks = {check["name"]: check["status"] for check in diagnosis["checks"]}
            self.assertEqual("pass", checks["plugin_manifest"])
            self.assertEqual("pass", checks["native_hooks"])
            self.assertEqual("warn", checks["mcp_environment"])

            fixture_world, fixture_walnut = make_world(root / "private-preflight")
            preflight = subprocess.run(
                [
                    "bash",
                    str(cache_root / "scripts" / "e2e_codex_sessions.sh"),
                    "--codex-bin",
                    str(CODEX_BIN),
                    "--codex-home",
                    str(codex_home),
                    "--plugin-root",
                    str(cache_root),
                    "--source-world",
                    str(fixture_world),
                    "--source-walnut",
                    str(fixture_walnut),
                    "--run-root",
                    str(root / "private-preflight-run"),
                    "--evidence",
                    str(root / "private-preflight-evidence.json"),
                    "--classification",
                    "private",
                    "--token",
                    "installed-preflight",
                    "--prepare-only",
                ],
                text=True,
                capture_output=True,
                env={**os.environ, "CODEX_HOME": str(codex_home)},
                timeout=20,
            )
            self.assertEqual(0, preflight.returncode, preflight.stderr)
            preflight_evidence = json.loads(preflight.stdout)
            self.assertEqual("prepared", preflight_evidence["status"])
            self.assertEqual("minimum", preflight_evidence["export_profile"])
            self.assertFalse(preflight_evidence["private_context_sent"])

            reinstalled = self.run_script(
                "install.sh", codex_home=codex_home, marketplace=marketplace
            )
            self.assertEqual(0, reinstalled.returncode, reinstalled.stderr)
            self.assertIn(json.loads(reinstalled.stdout)["status"], {"installed", "unchanged"})

            upgraded = self.run_script(
                "upgrade.sh", codex_home=codex_home, marketplace=marketplace
            )
            self.assertEqual(0, upgraded.returncode, upgraded.stderr)
            self.assertEqual("upgraded", json.loads(upgraded.stdout)["status"])

            removed = self.run_script(
                "uninstall.sh",
                codex_home=codex_home,
                marketplace=marketplace,
                extra=["--remove-marketplace"],
            )
            self.assertEqual(0, removed.returncode, removed.stderr)
            self.assertEqual("uninstalled", json.loads(removed.stdout)["status"])
            self.assertFalse(cache_root.exists())
            config = codex_home.joinpath("config.toml").read_text(encoding="utf-8")
            self.assertIn('custom_sentinel = "keep-me"', config)
            self.assertEqual("user world", world.joinpath("KEEP.txt").read_text())

    def test_install_refuses_a_second_enabled_alive_product(self) -> None:
        self.assertTrue(CODEX_BIN.is_file())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marketplace = root / "marketplace"
            build = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--plugin-root",
                    str(PLUGIN_ROOT),
                    "--output",
                    str(marketplace),
                ],
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(0, build.returncode, build.stderr)
            codex_home = root / "codex-home"
            codex_home.mkdir()
            codex_home.joinpath("config.toml").write_text(
                '[plugins."alive@alivecontext"]\nenabled = true\n',
                encoding="utf-8",
            )

            result = self.run_script(
                "install.sh", codex_home=codex_home, marketplace=marketplace
            )
            self.assertNotEqual(0, result.returncode)
            self.assertIn("alive@alivecontext", result.stderr)
            self.assertIn("only one ALIVE product", result.stderr)


if __name__ == "__main__":
    unittest.main()
