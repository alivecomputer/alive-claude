from __future__ import annotations

import ast
import errno
import multiprocessing
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "alive" / "scripts"

sys.path.insert(0, str(SCRIPTS))
import _common as common  # noqa: E402


def _child_hold_lock(lock_path: str, ready_path: str, release_path: str) -> None:
    """Hold flock_file until *release_path* appears. Spawn-safe (own sys.path)."""
    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(SCRIPTS))
    import _common as _common  # noqa: PLC0415

    with _common.flock_file(lock_path, timeout_seconds=5.0, retry_interval=0.05):
        _Path(ready_path).write_text("ready", encoding="utf-8")
        deadline = time.time() + 5.0
        while not _Path(release_path).exists():
            if time.time() >= deadline:
                return
            time.sleep(0.05)


class _FakeMsvcrt:
    """Minimal msvcrt.locking stand-in for Linux CI (no real MINGW)."""

    LK_NBLCK = 2
    LK_UNLCK = 3

    def __init__(self) -> None:
        self.holders = 0

    def locking(self, fd, mode, nbytes):  # noqa: ARG002
        if mode == self.LK_NBLCK:
            if self.holders:
                raise OSError(errno.EACCES, "Permission denied")
            self.holders += 1
            return None
        if mode == self.LK_UNLCK:
            self.holders = max(0, self.holders - 1)
            return None
        raise OSError(errno.EINVAL, "unknown lock mode")


class FileLockRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base = Path(self.tempdir.name)

    def test_common_and_log_do_not_bare_import_fcntl(self) -> None:
        # Native Windows CPython: a module-level `import fcntl` (not inside
        # try) is ModuleNotFoundError. try/except import is the fix.
        for name in ("_common.py", "log.py"):
            src = (SCRIPTS / name).read_text(encoding="utf-8")
            tree = ast.parse(src)
            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotEqual(
                            alias.name,
                            "fcntl",
                            "{} has an unguarded import fcntl".format(name),
                        )
                if isinstance(node, ast.ImportFrom) and node.module == "fcntl":
                    self.fail("{} imports from fcntl at module level".format(name))

    def test_missing_backend_is_not_a_silent_noop(self) -> None:
        orig_f, orig_m = common._fcntl, common._msvcrt
        try:
            common._fcntl = None
            common._msvcrt = None
            with self.assertRaises(RuntimeError) as ctx:
                common._lock_exclusive_nb(0)
            self.assertIn("fcntl", str(ctx.exception))
            self.assertIn("msvcrt", str(ctx.exception))
        finally:
            common._fcntl, common._msvcrt = orig_f, orig_m

    def test_msvcrt_backend_serializes_and_times_out(self) -> None:
        fake = _FakeMsvcrt()
        orig_f, orig_m = common._fcntl, common._msvcrt
        lock = self.base / "win.lock"
        try:
            common._fcntl = None
            common._msvcrt = fake
            with common.flock_file(str(lock), timeout_seconds=2.0):
                self.assertEqual(fake.holders, 1)
                with self.assertRaises(common.FlockTimeoutError):
                    with common.flock_file(
                        str(lock), timeout_seconds=0.25, retry_interval=0.05
                    ):
                        pass
            self.assertEqual(fake.holders, 0)
        finally:
            common._fcntl, common._msvcrt = orig_f, orig_m

    def test_msvcrt_lock_helpers_translate_contention(self) -> None:
        fake = _FakeMsvcrt()
        fd = os.open(str(self.base / "region.lock"), os.O_RDWR | os.O_CREAT, 0o644)
        try:
            common.msvcrt_lock_exclusive_nb(fd, fake)
            with self.assertRaises(BlockingIOError):
                common.msvcrt_lock_exclusive_nb(fd, fake)
            common.msvcrt_unlock(fd, fake)
            common.msvcrt_lock_exclusive_nb(fd, fake)
            common.msvcrt_unlock(fd, fake)
        finally:
            os.close(fd)

    def test_flock_file_serializes_two_processes(self) -> None:
        # Real fcntl path on Linux CI. Threads share a flock, so this
        # must be a second process.
        lock = str(self.base / "posix.lock")
        ready = str(self.base / "ready")
        release = str(self.base / "release")
        proc = multiprocessing.Process(
            target=_child_hold_lock, args=(lock, ready, release)
        )
        proc.start()
        deadline = time.time() + 5.0
        while not Path(ready).exists():
            if time.time() >= deadline:
                proc.terminate()
                proc.join(1)
                self.fail("child never acquired the lock")
            time.sleep(0.05)
        with self.assertRaises(common.FlockTimeoutError):
            with common.flock_file(lock, timeout_seconds=0.3, retry_interval=0.05):
                pass
        Path(release).write_text("go", encoding="utf-8")
        proc.join(5)
        self.assertEqual(proc.exitcode, 0)


if __name__ == "__main__":
    unittest.main()
