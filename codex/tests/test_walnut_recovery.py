from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_hook_runtime import make_world


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
E2E = PLUGIN_ROOT / "tests" / "e2e_walnut_process.py"


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class WalnutRecoveryTests(unittest.TestCase):
    def test_saved_change_is_recovered_by_a_distinct_process(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_world, source_walnut = make_world(root / "source")
            source_digest = tree_digest(source_world)
            session_world = root / "session-world"
            shutil.copytree(source_world, session_world)
            session_walnut = session_world / source_walnut.relative_to(source_world)
            token = "alpha-recovery-7f3c9a"
            evidence = root / "session-one.json"

            saved = subprocess.run(
                [
                    sys.executable,
                    str(E2E),
                    "save",
                    "--plugin-root",
                    str(PLUGIN_ROOT),
                    "--world",
                    str(session_world),
                    "--walnut",
                    str(session_walnut),
                    "--session",
                    "process-one",
                    "--token",
                    token,
                    "--evidence",
                    str(evidence),
                ],
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(0, saved.returncode, saved.stderr)
            save_result = json.loads(saved.stdout)
            self.assertEqual("saved", save_result["status"])
            self.assertTrue(evidence.is_file())

            recovered = subprocess.run(
                [
                    sys.executable,
                    str(E2E),
                    "recover",
                    "--plugin-root",
                    str(PLUGIN_ROOT),
                    "--world",
                    str(session_world),
                    "--walnut",
                    str(session_walnut),
                    "--session",
                    "process-two",
                    "--token",
                    token,
                ],
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(0, recovered.returncode, recovered.stderr)
            recovery = json.loads(recovered.stdout)
            self.assertEqual("recovered", recovery["status"])
            self.assertEqual("process-two", recovery["session"])
            self.assertTrue(recovery["decision_found"])
            self.assertTrue(recovery["task_found"])
            self.assertTrue(recovery["projection_found"])
            self.assertEqual(source_digest, tree_digest(source_world))


if __name__ == "__main__":
    unittest.main()
