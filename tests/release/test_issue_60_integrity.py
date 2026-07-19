from __future__ import annotations

import json
import importlib.util
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "plugins" / "alive" / "scripts" / "tasks.py"
SEEDED_WALNUT = (
    ROOT
    / "plugins"
    / "alive"
    / "skills"
    / "demo"
    / "preset"
    / "realistic-seeded"
    / "04_Ventures"
    / "nova-station"
)


def load_log_module():
    path = ROOT / "plugins" / "alive" / "scripts" / "log.py"
    spec = importlib.util.spec_from_file_location("alive_log_cli", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ALIVE_LOG = load_log_module()


def run_tasks(*arguments: str) -> list[dict[str, object]]:
    result = subprocess.run(
        [sys.executable, str(TASKS), "list", *arguments],
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"tasks.py exited {result.returncode}: {result.stderr}\n{result.stdout}"
        )
    return json.loads(result.stdout)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class CompletedTaskListingRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.base = Path(self.tempdir.name)

    def make_walnut(self, relative: str = "04_Ventures/sample") -> Path:
        walnut = self.base / "world" / relative
        (walnut / "_kernel").mkdir(parents=True)
        (walnut / "_kernel" / "key.md").write_text(
            "---\nname: Sample\n---\n", encoding="utf-8"
        )
        write_json(
            walnut / "_kernel" / "tasks.json",
            {
                "tasks": [
                    {
                        "id": "t-open",
                        "title": "Open task",
                        "status": "active",
                        "priority": "active",
                    }
                ]
            },
        )
        write_json(
            walnut / "_kernel" / "completed.json",
            {
                "completed": [
                    {
                        "id": "t-done-launch",
                        "title": "Finished launch work",
                        "status": "done",
                        "bundle": "launch",
                    },
                    {
                        "id": "t-done-other",
                        "title": "Finished other work",
                        "status": "done",
                        "bundle": "other",
                    },
                    {
                        "id": "t-dropped",
                        "title": "Dropped work",
                        "status": "dropped",
                        "bundle": "launch",
                    },
                ]
            },
        )
        return walnut

    def test_list_done_reads_seeded_completed_file(self) -> None:
        completed = json.loads(
            (SEEDED_WALNUT / "_kernel" / "completed.json").read_text(
                encoding="utf-8"
            )
        )["completed"]

        listed = run_tasks("--walnut", str(SEEDED_WALNUT), "--status", "done")

        self.assertGreater(len(completed), 0)
        self.assertEqual(
            {task["id"] for task in listed},
            {task["id"] for task in completed},
        )

    def test_list_done_applies_bundle_filter_to_completed_records(self) -> None:
        walnut = self.make_walnut()

        listed = run_tasks(
            "--walnut",
            str(walnut),
            "--status",
            "done",
            "--bundle",
            "launch",
        )

        self.assertEqual([task["id"] for task in listed], ["t-done-launch"])

    def test_list_dropped_reads_only_dropped_completed_records(self) -> None:
        walnut = self.make_walnut()

        listed = run_tasks("--walnut", str(walnut), "--status", "dropped")

        self.assertEqual([task["id"] for task in listed], ["t-dropped"])

    def test_default_list_stays_limited_to_open_work(self) -> None:
        walnut = self.make_walnut()

        listed = run_tasks("--walnut", str(walnut))

        self.assertEqual([task["id"] for task in listed], ["t-open"])

    def test_world_done_list_adds_attribution_without_mutating_history(self) -> None:
        world = self.base / "world"
        (world / ".alive").mkdir(parents=True)
        first = self.make_walnut("04_Ventures/first")
        second = self.make_walnut("05_Experiments/second")
        before = {
            walnut: (walnut / "_kernel" / "completed.json").read_bytes()
            for walnut in (first, second)
        }

        listed = run_tasks("--world", str(world), "--status", "done")

        self.assertEqual(len(listed), 4)
        self.assertEqual(
            {task["walnut"] for task in listed},
            {"04_Ventures/first", "05_Experiments/second"},
        )
        for walnut, original in before.items():
            self.assertEqual(
                (walnut / "_kernel" / "completed.json").read_bytes(), original
            )


class LogIntegrityRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.original = (SEEDED_WALNUT / "_kernel" / "log.md").read_text(
            encoding="utf-8"
        )
        self.envelope, self.rest = ALIVE_LOG._split_frontmatter(self.original)
        self.old_entry_count = ALIVE_LOG._find_entry_count(self.envelope)

    def compute(self, summary: str = "Regression probe") -> str:
        return ALIVE_LOG._compute_new_log(
            self.envelope,
            self.rest,
            self.old_entry_count + 1,
            "2026-07-20T00:00:00+00:00",
            summary,
            "deadbeef",
            "Recorded a bounded regression probe.",
            "feedface",
        )

    def test_prepend_preserves_previous_log_remainder_byte_for_byte(self) -> None:
        before_headings = re.findall(r"^## ", self.rest, flags=re.MULTILINE)

        rewritten = self.compute()

        self.assertTrue(rewritten.endswith(self.rest))
        self.assertEqual(
            len(re.findall(r"^## ", rewritten, flags=re.MULTILINE)),
            len(before_headings) + 1,
        )

    def test_summary_is_single_line_escaped_and_has_no_save_count(self) -> None:
        rewritten = self.compute('Line "quoted" \\ path\nsecond line')
        envelope, _rest = ALIVE_LOG._split_frontmatter(rewritten)
        summary_lines = [line for line in envelope if line.startswith("summary:")]

        self.assertEqual(len(summary_lines), 1)
        self.assertIn(r'\"quoted\"', summary_lines[0])
        self.assertIn(r"\\ path", summary_lines[0])
        self.assertIn(r"\nsecond line", summary_lines[0])
        self.assertNotIn("\n", summary_lines[0])
        self.assertFalse(any("save-count" in line for line in envelope))


if __name__ == "__main__":
    unittest.main()
