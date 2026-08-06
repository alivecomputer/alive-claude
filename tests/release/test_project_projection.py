from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "alive" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import project  # noqa: E402


class ProjectPhaseExtractionRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.walnut = Path(self.tempdir.name) / "walnut"
        (self.walnut / "_kernel").mkdir(parents=True)

    def write_log(self, body: str) -> None:
        (self.walnut / "_kernel" / "log.md").write_text(
            "---\nentry-count: 1\n---\n\n"
            "## 2026-07-20T00:00:00+00:00 — squirrel:deadbeef\n\n"
            + body
            + "\n",
            encoding="utf-8",
        )

    def test_phase_token_inside_narrative_prose_is_not_treated_as_a_field(self) -> None:
        self.write_log(
            "We revisited the phase: still early design work and vendor research."
        )

        parsed = project.parse_log(str(self.walnut))

        self.assertEqual(parsed["phase"], "research")

    def test_anchored_known_phase_field_is_accepted(self) -> None:
        self.write_log("phase: testing\n\nThe import harness passed.")

        parsed = project.parse_log(str(self.walnut))

        self.assertEqual(parsed["phase"], "testing")

    def test_anchored_unknown_phase_falls_back_to_narrative_vocabulary(self) -> None:
        self.write_log(
            "phase: still early design work and vendor research\n\n"
            "The team is building the import harness."
        )

        parsed = project.parse_log(str(self.walnut))

        self.assertEqual(parsed["phase"], "building")


if __name__ == "__main__":
    unittest.main()
