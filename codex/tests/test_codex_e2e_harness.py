from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.test_hook_runtime import make_world


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
E2E = PLUGIN_ROOT / "scripts" / "e2e_codex_sessions.py"
E2E_SHELL = PLUGIN_ROOT / "scripts" / "e2e_codex_sessions.sh"


class CodexE2EHarnessTests(unittest.TestCase):
    def make_fake_codex(self, root: Path) -> Path:
        fake = root / "fake-codex"
        fake.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import json
                import pathlib
                import re
                import sys

                output = pathlib.Path(sys.argv[sys.argv.index("--output-last-message") + 1])
                world = pathlib.Path(sys.argv[sys.argv.index("--cd") + 1])
                walnut = next(path.parent.parent for path in world.rglob("_kernel/key.md"))
                kernel = walnut / "_kernel"
                phase = "save" if "session-one" in output.name else "recover"
                prompt = sys.argv[-1]
                if phase == "save":
                    token = re.search(r"ALIVE_CODEX_E2E_[A-Za-z0-9_-]+", prompt).group(0)
                else:
                    token = re.search(
                        r"ALIVE_CODEX_E2E_[A-Za-z0-9_-]+",
                        (kernel / "log.md").read_text(),
                    ).group(0)
                decision = f"Decision: preserve {token} across Codex sessions."
                task_title = f"Recover {token} in a new Codex session"
                if phase == "save":
                    log = kernel / "log.md"
                    log.write_text(log.read_text() + "\\n" + decision + "\\n")
                    (kernel / "tasks.json").write_text(json.dumps({"tasks": [{"title": task_title}]}) + "\\n")
                    (kernel / "now.json").write_text(json.dumps({"context": decision, "next": task_title}) + "\\n")
                log_text = (kernel / "log.md").read_text()
                tasks_text = (kernel / "tasks.json").read_text()
                now_text = (kernel / "now.json").read_text()
                result = {
                    "phase": phase,
                    "token": token,
                    "decision_found": decision in log_text,
                    "task_found": task_title in tasks_text,
                    "projection_found": token in now_text,
                    "saved": phase == "save",
                }
                output.write_text(json.dumps(result) + "\\n")
                print(json.dumps({"type": "fake_codex", "phase": phase, "argv": sys.argv[1:]}))
                """
            ),
            encoding="utf-8",
        )
        fake.chmod(0o755)
        return fake

    def command(
        self,
        *,
        root: Path,
        fake_codex: Path,
        world: Path,
        walnut: Path,
        classification: str,
        authorize: bool = False,
        extra: list[str] | None = None,
    ) -> list[str]:
        command = [
            sys.executable,
            str(E2E),
            "--codex-bin",
            str(fake_codex),
            "--codex-home",
            str(root / "codex-home"),
            "--plugin-root",
            str(PLUGIN_ROOT),
            "--source-world",
            str(world),
            "--source-walnut",
            str(walnut),
            "--run-root",
            str(root / "run"),
            "--evidence",
            str(root / "evidence.json"),
            "--classification",
            classification,
            "--token",
            "synthetic-e2e-token",
            "--timeout",
            "10",
        ]
        if authorize:
            command.extend(
                [
                    "--authorize-private-export",
                    "I_AUTHORIZE_PRIVATE_WALNUT_EXPORT",
                ]
            )
        command.extend(extra or [])
        return command

    def test_private_context_is_blocked_without_exact_authorization(self) -> None:
        self.assertTrue(E2E.is_file(), "model-backed E2E runner is missing")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root / "fixture")
            result = subprocess.run(
                self.command(
                    root=root,
                    fake_codex=self.make_fake_codex(root),
                    world=world,
                    walnut=walnut,
                    classification="private",
                ),
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(77, result.returncode, result.stderr)
            evidence = json.loads(root.joinpath("evidence.json").read_text())
            self.assertEqual("blocked", evidence["status"])
            self.assertEqual("private_export_authorization_missing", evidence["reason"])
            self.assertFalse(root.joinpath("run").exists())

    def test_synthetic_two_process_run_requires_disk_and_recovery_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root / "fixture")
            source_log = walnut.joinpath("_kernel", "log.md").read_bytes()
            result = subprocess.run(
                self.command(
                    root=root,
                    fake_codex=self.make_fake_codex(root),
                    world=world,
                    walnut=walnut,
                    classification="synthetic",
                ),
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            evidence = json.loads(root.joinpath("evidence.json").read_text())
            self.assertEqual("pass", evidence["status"])
            self.assertTrue(evidence["session_one"]["disk_saved"])
            self.assertTrue(evidence["session_two"]["decision_found"])
            self.assertTrue(evidence["session_two"]["task_found"])
            self.assertTrue(evidence["session_two"]["projection_found"])
            self.assertTrue(evidence["session_two"]["kernel_unchanged"])
            self.assertEqual(
                "recover", evidence["session_two"]["last_message"]["phase"]
            )
            self.assertFalse(evidence["session_two"]["last_message"]["saved"])
            self.assertNotEqual(
                evidence["session_one"]["process_id"],
                evidence["session_two"]["process_id"],
            )
            self.assertTrue(evidence["ephemeral_sessions"])
            self.assertEqual(source_log, walnut.joinpath("_kernel", "log.md").read_bytes())

    def test_private_export_defaults_to_an_allowlisted_minimum_disclosure_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root / "fixture")
            private_inbox = world / "03_Inbox" / "must-not-export.txt"
            private_inbox.parent.mkdir(parents=True, exist_ok=True)
            private_inbox.write_text("unrelated private material\n", encoding="utf-8")
            private_session = walnut / "_kernel" / "sessions" / "must-not-export.jsonl"
            private_session.parent.mkdir(parents=True, exist_ok=True)
            private_session.write_text('{"private": true}\n', encoding="utf-8")

            result = subprocess.run(
                self.command(
                    root=root,
                    fake_codex=self.make_fake_codex(root),
                    world=world,
                    walnut=walnut,
                    classification="private",
                    authorize=True,
                ),
                text=True,
                capture_output=True,
                timeout=20,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            evidence = json.loads(root.joinpath("evidence.json").read_text())
            self.assertEqual("minimum", evidence["export_profile"])
            self.assertTrue(evidence["private_context_sent"])
            manifest_path = Path(evidence["disclosure_manifest"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            disclosed = {entry["path"] for entry in manifest["files"]}
            expected = {
                ".alive/key.md",
                "04_Ventures/demo-walnut/_kernel/insights.md",
                "04_Ventures/demo-walnut/_kernel/key.md",
                "04_Ventures/demo-walnut/_kernel/log.md",
                "04_Ventures/demo-walnut/_kernel/tasks.json",
            }
            self.assertEqual(expected, disclosed)
            self.assertEqual(len(expected), evidence["disclosed_file_count"])
            origins = {entry["path"]: entry["origin"] for entry in manifest["files"]}
            self.assertEqual("source", origins["04_Ventures/demo-walnut/_kernel/key.md"])
            self.assertEqual("source", origins["04_Ventures/demo-walnut/_kernel/insights.md"])
            self.assertEqual("generated", origins[".alive/key.md"])
            self.assertEqual("generated", origins["04_Ventures/demo-walnut/_kernel/log.md"])
            self.assertEqual("generated", origins["04_Ventures/demo-walnut/_kernel/tasks.json"])
            self.assertFalse((root / "run" / "World" / "03_Inbox" / private_inbox.name).exists())
            self.assertFalse(
                (root / "run" / "World" / "04_Ventures" / "demo-walnut" / "_kernel" / "sessions" / private_session.name).exists()
            )

    def test_private_local_provider_never_claims_external_context_was_sent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root / "fixture")
            local_only = walnut / "_kernel" / "sessions" / "local-history.jsonl"
            local_only.parent.mkdir(parents=True, exist_ok=True)
            local_only.write_text('{"local": true}\n', encoding="utf-8")
            result = subprocess.run(
                self.command(
                    root=root,
                    fake_codex=self.make_fake_codex(root),
                    world=world,
                    walnut=walnut,
                    classification="private",
                    extra=[
                        "--local-provider",
                        "ollama",
                        "--model",
                        "local-test-model",
                    ],
                ),
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            evidence = json.loads(root.joinpath("evidence.json").read_text())
            self.assertEqual("local:ollama", evidence["model_transport"])
            self.assertEqual("local-test-model", evidence["model"])
            self.assertEqual("whole-world-local", evidence["export_profile"])
            self.assertFalse(evidence["private_context_sent"])
            self.assertTrue(
                (root / "run" / "World" / "04_Ventures" / "demo-walnut" / "_kernel" / "sessions" / local_only.name).is_file()
            )
            event_text = Path(evidence["session_one"]["events"]).read_text()
            self.assertIn('"--oss"', event_text)
            self.assertIn('"ollama"', event_text)

    def test_prepare_only_builds_manifest_without_sending_private_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            world, walnut = make_world(root / "fixture")
            result = subprocess.run(
                self.command(
                    root=root,
                    fake_codex=self.make_fake_codex(root),
                    world=world,
                    walnut=walnut,
                    classification="private",
                    extra=["--prepare-only"],
                ),
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            evidence = json.loads(root.joinpath("evidence.json").read_text())
            self.assertEqual("prepared", evidence["status"])
            self.assertEqual("minimum", evidence["export_profile"])
            self.assertFalse(evidence["private_context_sent"])
            self.assertTrue(Path(evidence["disclosure_manifest"]).is_file())
            self.assertFalse(root.joinpath("run", "session-one-events.jsonl").exists())

    def test_shell_entrypoint_is_executable_and_forwards_to_python_runner(self) -> None:
        self.assertTrue(os.access(E2E_SHELL, os.X_OK))
        shell = E2E_SHELL.read_text(encoding="utf-8")
        self.assertIn("e2e_codex_sessions.py", shell)

    def test_runner_closes_codex_stdin_for_noninteractive_execution(self) -> None:
        runner = E2E.read_text(encoding="utf-8")
        self.assertIn("stdin=subprocess.DEVNULL", runner)

    def test_prompts_define_literal_token_and_projection_semantics(self) -> None:
        runner = E2E.read_text(encoding="utf-8")
        self.assertIn("Do not create a token-named file", runner)
        self.assertIn("token must be the exact bare ALIVE_CODEX_E2E_ value", runner)
        self.assertIn("projection_found is true exactly when", runner)
        self.assertIn("_kernel/now.json", runner)
        self.assertIn("Do not edit _kernel/tasks.json or _kernel/now.json directly", runner)
        self.assertIn("--priority active", runner)

    def test_disk_state_reports_missing_kernel_files_as_false(self) -> None:
        spec = importlib.util.spec_from_file_location("alive_e2e_runner", E2E)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        with tempfile.TemporaryDirectory() as directory:
            _, walnut = make_world(Path(directory))
            walnut.joinpath("_kernel", "tasks.json").unlink()
            state = runner.disk_state(walnut, "ALIVE_CODEX_E2E_MISSING")
            self.assertFalse(state["task_found"])
            self.assertFalse(state["decision_found"])
            self.assertFalse(state["projection_found"])


if __name__ == "__main__":
    unittest.main()
