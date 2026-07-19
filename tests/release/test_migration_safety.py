from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "plugins" / "alive" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from system_upgrade.migrations import v2_to_v3_0  # noqa: E402


class MigrationFallbackSafetyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.world = Path(self.tempdir.name) / "world"
        self.world.mkdir()

    def test_fallback_requires_identity_before_treating_bundles_as_walnut(self) -> None:
        (self.world / "project" / "bundles" / "assets").mkdir(parents=True)

        real = self.world / "04_Ventures" / "real"
        (real / "_kernel").mkdir(parents=True)
        (real / "_kernel" / "key.md").write_text("name: real\n", encoding="utf-8")
        (real / "bundles" / "launch").mkdir(parents=True)

        discovered = v2_to_v3_0._resolve_walnuts(str(self.world), None)

        self.assertEqual(discovered, [str(real)])

    def test_fallback_keeps_support_for_legacy_identity_triple(self) -> None:
        legacy = self.world / "legacy-project"
        legacy.mkdir()
        for name in ("companion.md", "now.md", "tasks.md"):
            (legacy / name).write_text(f"# {name}\n", encoding="utf-8")
        (legacy / "bundles" / "launch").mkdir(parents=True)

        discovered = v2_to_v3_0._resolve_walnuts(str(self.world), None)

        self.assertEqual(discovered, [str(legacy)])


if __name__ == "__main__":
    unittest.main()
