from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "plugins" / "alive" / "hooks" / "scripts" / "alive-common.sh"
SCRIPTS = ROOT / "plugins" / "alive" / "scripts"
HOOKS = ROOT / "plugins" / "alive" / "hooks" / "scripts"

sys.path.insert(0, str(SCRIPTS))
from _world_root_io import lexical_normalize_path, windows_drive_to_msys  # noqa: E402


def _bash(script: str, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", "-c", script, "bash", *args],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
        env=env,
    )


def _normalize_after_source(raw_path: str, prelude: str = "") -> subprocess.CompletedProcess[str]:
    """Source alive-common.sh then normalize. *prelude* runs BEFORE source.

    SessionStart does not pass ALIVE_PLATFORM; the hook computes it while
    sourcing. Tests that want MINGW64 must set OSTYPE/MSYSTEM/MACHTYPE in
    *prelude*, not after source -- bash overwrites OSTYPE at process
    start, so a parent-env OSTYPE=msys never reaches Linux bash.
    """
    return _bash(
        prelude + 'source "$1"; printf "PLATFORM=%s\\n" "$ALIVE_PLATFORM"; lexical_normalize_path "$2"',
        str(COMMON),
        raw_path,
    )


class MingwPlatformDetectionTest(unittest.TestCase):
    """alive#67: the 3.2.1 convert is gated on ALIVE_PLATFORM=windows.

    SessionStart runs `bash .../alive-session-new.sh` (hooks.json) and
    sources alive-common.sh. Claude does not set the flag. If detection
    misses MINGW64, the convert is dead.
    """

    def test_ostype_msys_sets_windows_and_converts_backslash_path(self) -> None:
        result = _normalize_after_source(
            r"C:\Users\Ada\Alive World",
            prelude='OSTYPE=msys; MSYSTEM=MINGW64; MACHTYPE=x86_64-pc-cygwin; ',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(lines[0], "PLATFORM=windows")
        self.assertEqual(lines[-1], "/c/Users/Ada/Alive World")

    def test_ostype_msys2_prefix_sets_windows(self) -> None:
        # Exact `OSTYPE == msys` (3.2.1) misses this; prefix match must not.
        result = _normalize_after_source(
            r"C:\Users\Ada\alive",
            prelude="OSTYPE=msys2; ",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLATFORM=windows", result.stdout)
        self.assertTrue(result.stdout.strip().endswith("/c/Users/Ada/alive"))

    def test_msystem_mingw64_sets_windows_even_if_ostype_looks_unix(self) -> None:
        result = _normalize_after_source(
            "D:/Context/World",
            prelude="OSTYPE=linux-gnu; MSYSTEM=MINGW64; ",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLATFORM=windows", result.stdout)
        self.assertTrue(result.stdout.strip().endswith("/d/Context/World"))

    def test_machtype_cygwin_sets_windows(self) -> None:
        result = _normalize_after_source(
            r"C:\Users\Ada\alive",
            prelude="OSTYPE=linux-gnu; unset MSYSTEM; MACHTYPE=x86_64-pc-cygwin; ",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PLATFORM=windows", result.stdout)

    def test_linux_source_leaves_unix_and_rejects_drive_path(self) -> None:
        result = _normalize_after_source(
            r"C:\Users\Ada\alive",
            prelude="OSTYPE=linux-gnu; unset MSYSTEM; MACHTYPE=x86_64-pc-linux-gnu; ",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("PLATFORM=unix", result.stdout)


class BashWorldRootPathRegressionTest(unittest.TestCase):
    """Convert itself: C:\\ and C:/ both become /c/... when the flag is set.

    Public 3.2.1 already had this convert. These tests exercise it the way
    SessionStart does (flag from detection), plus mixed separators.
    """

    def normalize_as_windows(self, raw_path: str) -> subprocess.CompletedProcess[str]:
        return _bash(
            'source "$1"; ALIVE_PLATFORM=windows; lexical_normalize_path "$2"',
            str(COMMON),
            raw_path,
        )

    def test_native_windows_backslash_path_converts_to_msys_mount(self) -> None:
        result = self.normalize_as_windows(r"C:\Users\Ada\Alive World")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/c/Users/Ada/Alive World")

    def test_native_windows_forward_slash_path_converts_to_msys_mount(self) -> None:
        result = self.normalize_as_windows("D:/Context/World")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/d/Context/World")

    def test_mixed_separators_fold_to_msys_mount(self) -> None:
        result = self.normalize_as_windows(r"C:\Users/Ada\world")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/c/Users/Ada/world")

    def test_posix_absolute_path_is_unchanged(self) -> None:
        result = self.normalize_as_windows("/home/ada/alive")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/home/ada/alive")

    def test_relative_path_still_rejected(self) -> None:
        result = self.normalize_as_windows("Users/Ada/alive")
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_persisted_windows_config_is_not_corrupt_when_platform_is_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "world-root"
            cfg.write_text(r"C:\Users\Ada\Alive World" + "\n", encoding="utf-8")
            result = _bash(
                'OSTYPE=msys; MSYSTEM=MINGW64; source "$1"; _alive_parse_persisted_world_root_file "$2"',
                str(COMMON),
                str(cfg),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "/c/Users/Ada/Alive World")

    def test_python_helper_matches_bash_windows_convert(self) -> None:
        cases = (
            (r"C:\Users\Ada\Alive World", "/c/Users/Ada/Alive World"),
            ("C:/Users/Ada/Alive World", "/c/Users/Ada/Alive World"),
            (r"C:\Users/Ada\world", "/c/Users/Ada/world"),
            (r"e:\alive", "/e/alive"),
        )
        for raw, expected in cases:
            self.assertEqual(windows_drive_to_msys(raw), expected, raw)
            result = self.normalize_as_windows(raw)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)

    def test_python_helper_leaves_posix_and_relative_alone(self) -> None:
        self.assertIsNone(windows_drive_to_msys("/home/ada/alive"))
        self.assertIsNone(windows_drive_to_msys("Users/Ada"))
        self.assertIsNone(windows_drive_to_msys("C:Users"))
        self.assertIsNone(windows_drive_to_msys(""))

    def test_python_lexical_normalize_does_not_rewrite_drive_paths_on_posix(self) -> None:
        # write_world_root_file calls lexical_normalize_path. Folding C:\
        # into /c/ here would persist an MSYS path that native Windows
        # Python doctor then treats as C:\c\... .
        if os.name == "nt":
            self.skipTest("native Windows os.path already accepts C:\\")
        with self.assertRaises(ValueError):
            lexical_normalize_path(r"C:\Users\Ada\alive")
        with self.assertRaises(ValueError):
            lexical_normalize_path("C:/Users/Ada/alive")


class StatuslineJsonEncodeTest(unittest.TestCase):
    def encode(self, value: str) -> subprocess.CompletedProcess[str]:
        return _bash(
            'source "$1"; alive_json_encode_string "$2"',
            str(COMMON),
            value,
        )

    def test_encode_round_trips_spaces_and_quotes(self) -> None:
        raw = 'bash "/c/Users/Ada/Alive World/.alive/statusline.sh"'
        result = self.encode(raw)
        self.assertEqual(result.returncode, 0, result.stderr)
        encoded = result.stdout.strip()
        self.assertEqual(json.loads(encoded), raw)

    def test_session_new_does_not_use_nested_double_quoted_python_c(self) -> None:
        text = (HOOKS / "alive-session-new.sh").read_text(encoding="utf-8")
        self.assertNotIn(
            'decode("utf-8","replace")))" 2>/dev/null',
            text,
        )
        self.assertIn("alive_json_encode_string", text)


if __name__ == "__main__":
    unittest.main()
