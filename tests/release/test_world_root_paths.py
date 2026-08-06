from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "plugins" / "alive" / "hooks" / "scripts" / "alive-common.sh"


class BashWorldRootPathRegressionTest(unittest.TestCase):
    def normalize_as_windows(self, raw_path: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "bash",
                "-c",
                'source "$1"; ALIVE_PLATFORM=windows; lexical_normalize_path "$2"',
                "bash",
                str(COMMON),
                raw_path,
            ],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )

    def test_native_windows_backslash_path_converts_to_msys_mount(self) -> None:
        result = self.normalize_as_windows(r"C:\Users\Ada\Alive World")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/c/Users/Ada/Alive World")

    def test_native_windows_forward_slash_path_converts_to_msys_mount(self) -> None:
        result = self.normalize_as_windows("D:/Context/World")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/d/Context/World")


if __name__ == "__main__":
    unittest.main()
