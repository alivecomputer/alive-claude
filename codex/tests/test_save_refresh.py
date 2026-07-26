from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_hook_runtime import make_world


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
REFRESH = PLUGIN_ROOT / "scripts" / "save-refresh.py"


def load_refresh_module():
    spec = importlib.util.spec_from_file_location("alive_save_refresh", REFRESH)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load save-refresh.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SaveRefreshTests(unittest.TestCase):
    def run_refresh(
        self, world: Path, *, walnut: Path | None = None, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, str(REFRESH), "--world", str(world)]
        if walnut is not None:
            command.extend(["--walnut", str(walnut)])
        return subprocess.run(
            command,
            text=True,
            capture_output=True,
            env={**os.environ, **(env or {})},
            timeout=15,
        )

    def test_active_walnut_refreshes_project_index_and_orientation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            world, walnut = make_world(Path(directory))
            result = self.run_refresh(world, walnut=walnut)
            self.assertEqual(0, result.returncode, result.stderr)
            index = world / ".alive" / "_index.json"
            orientation = world / ".alive" / "_orientation.json"
            self.assertTrue(walnut.joinpath("_kernel", "now.json").is_file())
            self.assertTrue(index.is_file())
            payload = json.loads(orientation.read_text(encoding="utf-8"))
            self.assertIs(type(payload["schema_version"]), int)
            self.assertEqual(1, payload["schema_version"])
            self.assertGreaterEqual(orientation.stat().st_mtime_ns, index.stat().st_mtime_ns)

    def test_orientation_failure_does_not_accept_a_stale_prior_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            world, walnut = make_world(Path(directory))
            first = self.run_refresh(world, walnut=walnut)
            self.assertEqual(0, first.returncode, first.stderr)
            index = world / ".alive" / "_index.json"
            orientation = world / ".alive" / "_orientation.json"
            prior = orientation.read_bytes()
            os.utime(orientation, (1, 1))
            os.utime(index, (2, 2))

            failed = self.run_refresh(
                world,
                walnut=walnut,
                env={"ALIVE_ORIENTATION_TEST_FAIL": "1"},
            )
            self.assertNotEqual(0, failed.returncode)
            self.assertIn("projection refresh is incomplete", failed.stderr.lower())
            self.assertEqual(prior, orientation.read_bytes())
            self.assertLess(orientation.stat().st_mtime_ns, index.stat().st_mtime_ns)

    def test_standalone_refresh_skips_project_and_refreshes_world_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            world, walnut = make_world(Path(directory))
            result = self.run_refresh(world)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("standalone", result.stdout.lower())
            self.assertFalse(walnut.joinpath("_kernel", "now.json").exists())
            self.assertTrue(world.joinpath(".alive", "_index.json").is_file())
            self.assertTrue(world.joinpath(".alive", "_orientation.json").is_file())

    def test_save_verification_rejects_same_stat_different_index_content(self) -> None:
        """Save completion must use digest identity, not only mtime ordering."""
        with tempfile.TemporaryDirectory() as directory:
            world, walnut = make_world(Path(directory))
            result = self.run_refresh(world, walnut=walnut)
            self.assertEqual(0, result.returncode, result.stderr)
            index = world / ".alive" / "_index.json"
            raw = index.read_bytes()
            stat = index.stat()
            mutated = raw.replace(b'"people": 0', b'"people": 9', 1)
            self.assertEqual(len(raw), len(mutated))
            index.write_bytes(mutated)
            os.utime(index, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            with self.assertRaisesRegex(RuntimeError, "strict.*identity"):
                load_refresh_module().verify_orientation(world)


if __name__ == "__main__":
    unittest.main()
