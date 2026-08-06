"""Regression tests for issues #72 and #73.

Issue #72: manifest readers looked only for a top-level ``status:`` key,
but bundle manifests declare their lifecycle as ``phase:`` (with an
inline YAML comment). Every bundle was pinned to the ``draft`` default
and inline comments leaked into field values.

Issue #73: ``tasks.py summary`` counted tasks with status ``done`` or
``dropped`` as urgent whenever their priority was ``urgent``, promoting
finished work into the active tier.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "plugins" / "alive" / "scripts" / "tasks.py"


def load_project_module():
    path = ROOT / "plugins" / "alive" / "scripts" / "project.py"
    spec = importlib.util.spec_from_file_location("alive_project_cli", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROJECT = load_project_module()


class SummaryRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.walnut = Path(self._tmp.name) / "walnut"
        kernel = self.walnut / "_kernel"
        kernel.mkdir(parents=True)
        (kernel / "key.md").write_text("# key\n", encoding="utf-8")
        (kernel / "tasks.json").write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "id": "u1",
                            "title": "kernel finished urgent",
                            "priority": "urgent",
                            "status": "done",
                        },
                        {
                            "id": "u2",
                            "title": "kernel open todo",
                            "priority": "normal",
                            "status": "todo",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        self.bundle = self.walnut / "my-bundle"
        self.bundle.mkdir()
        self.manifest = self.bundle / "context.manifest.yaml"
        self.manifest.write_text(
            'name: "my-bundle"\n'
            'goal: "ship the thing"\n'
            "phase: published  # draft | prototype | published | done\n"
            "due:  # optional - ISO date\n",
            encoding="utf-8",
        )
        (self.bundle / "tasks.json").write_text(
            json.dumps(
                {
                    "tasks": [
                        {
                            "id": "t1",
                            "title": "real urgent",
                            "priority": "urgent",
                            "status": "todo",
                        },
                        {
                            "id": "t2",
                            "title": "finished urgent",
                            "priority": "urgent",
                            "status": "done",
                        },
                        {
                            "id": "t3",
                            "title": "dropped urgent",
                            "priority": "urgent",
                            "status": "dropped",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_summary(self) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                str(TASKS),
                "summary",
                "--walnut",
                str(self.walnut),
                "--include-items",
            ],
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def bundle_entry(self, summary: dict) -> dict:
        bundles = summary["bundles"]
        entry = bundles.get("active", {}).get("my-bundle") or bundles.get(
            "recent", {}
        ).get("my-bundle")
        self.assertIsNotNone(entry, f"my-bundle missing from summary: {bundles}")
        return entry

    def test_issue_72_bundle_phase_is_not_pinned_to_draft(self) -> None:
        entry = self.bundle_entry(self.run_summary())
        self.assertEqual(entry["status"], "published")

    def test_issue_72_parse_manifest_reads_phase_and_ignores_comments(self) -> None:
        parsed = PROJECT.parse_manifest(str(self.manifest))
        self.assertEqual(parsed["status"], "published")
        self.assertEqual(parsed["goal"], "ship the thing")
        self.assertNotIn("due", parsed, "empty commented field must not leak")

    def test_issue_73_done_and_dropped_tasks_are_not_urgent(self) -> None:
        summary = self.run_summary()
        entry = self.bundle_entry(summary)
        counts = entry["tasks"]["counts"]
        self.assertEqual(counts["urgent"], 1)
        self.assertEqual(entry["tasks"]["urgent"], ["real urgent"])
        unscoped = summary["unscoped"]
        self.assertEqual(unscoped["counts"]["urgent"], 0)
        self.assertEqual(unscoped["urgent"], [])
        self.assertEqual(unscoped["counts"]["todo"], 1)


if __name__ == "__main__":
    unittest.main()
