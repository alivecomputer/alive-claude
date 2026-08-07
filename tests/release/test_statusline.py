from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATUSLINE = ROOT / "plugins" / "alive" / "statusline" / "alive-statusline.sh"


def run_statusline(world: Path, session_id: str, transcript: Path) -> subprocess.CompletedProcess[str]:
    payload = {
        "session_id": session_id,
        "cwd": str(world),
        "transcript_path": str(transcript),
        "model": {"display_name": "Test Model"},
        "cost": {"total_cost_usd": 0.01},
        "context_window": {"used_percentage": 1},
    }
    return subprocess.run(
        ["bash", str(STATUSLINE)],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        cwd=world,
        timeout=30,
        check=False,
    )


class StatuslineRegistrationRaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.world = Path(self.tempdir.name) / "world"
        (self.world / ".alive" / "_squirrels").mkdir(parents=True)
        self.transcript = Path(self.tempdir.name) / "session.jsonl"
        self.transcript.write_text("{}\n", encoding="utf-8")

    def test_fresh_transcript_softens_missing_entry_during_initialisation(self) -> None:
        result = run_statusline(self.world, "fresh-session", self.transcript)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("alive: initialising...", result.stdout)
        self.assertNotIn("session not registered", result.stdout)

    def test_stale_transcript_preserves_missing_registration_warning(self) -> None:
        stale = time.time() - 61
        os.utime(self.transcript, (stale, stale))

        result = run_statusline(self.world, "stale-session", self.transcript)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("session not registered", result.stdout)
        self.assertNotIn("alive: initialising...", result.stdout)


if __name__ == "__main__":
    unittest.main()
