from __future__ import annotations

import json
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


if __name__ == "__main__":
    unittest.main()
