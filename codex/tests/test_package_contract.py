from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build_marketplace import release_files


PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def plugin_errors(root: Path) -> list[str]:
    errors: list[str] = []
    files: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if name not in {".git", ".pytest_cache", ".venv", "__pycache__", "dist"}
        ]
        files.extend(Path(directory) / name for name in filenames)
    manifest_path = root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid manifest: {exc}"]

    if manifest.get("version") != "3.3.0-alpha.3":
        errors.append("manifest version must be 3.3.0-alpha.3")

    expected = {
        "skills": "./skills/",
        "mcpServers": "./.mcp.json",
    }
    for field, relative in expected.items():
        if manifest.get(field) != relative:
            errors.append(f"manifest {field} must equal {relative}")
        if not (root / relative).exists():
            errors.append(f"manifest {field} path does not exist: {relative}")

    if "hooks" in manifest:
        errors.append("manifest hooks is unsupported; hooks are discovered from hooks/hooks.json")
    capabilities = manifest.get("interface", {}).get("capabilities")
    if not isinstance(capabilities, list) or not all(
        isinstance(value, str) and value.strip() for value in capabilities
    ):
        errors.append("manifest interface.capabilities must be an array of strings")
    if not (root / "hooks" / "hooks.json").is_file():
        errors.append("auto-discovered hooks/hooks.json is missing")

    required = (
        "scripts/project.py",
        "scripts/tasks.py",
        "scripts/generate-index.py",
        "scripts/save-refresh.py",
        "scripts/generate-graph.py",
        "templates/walnut/key.md",
        "rules/world.md",
        "mcp/run.sh",
    )
    for relative in required:
        if not (root / relative).is_file():
            errors.append(f"required packaged file missing: {relative}")

    for script in sorted(path for path in files if path.suffix == ".sh"):
        if not os.access(script, os.X_OK):
            errors.append(f"shell script is not executable: {script.relative_to(root)}")

    forbidden = re.compile(
        r"/Users/[^/]+/aliveplugindev|CODEX_PLUGIN_ROOT|"
        r"(?:python3|bash)\s+[\"']?plugins/alive/scripts"
    )
    for path in sorted(files):
        if path.suffix in {".png", ".jpg", ".jpeg", ".pyc"}:
            continue
        if re.search(r" \d+(?:\.[^/]+)?$", path.name):
            errors.append(f"conflicted duplicate file found: {path.relative_to(root)}")
        if any(
            part in {"docs", "docs-internal", "dist", "tests", "__pycache__"}
            for part in path.parts
        ):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if forbidden.search(text):
            errors.append(f"checkout-only path found in {path.relative_to(root)}")

    return errors


def copy_release_contents(source_root: Path, destination_root: Path) -> None:
    """Copy only files the marketplace builder would put in an installation."""
    destination_root.mkdir(parents=True)
    for relative in release_files(source_root):
        source = source_root / relative
        destination = destination_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as input_handle, destination.open("wb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
        shutil.copymode(source, destination)


class PackageContractTests(unittest.TestCase):
    def diagnose_copy(
        self,
        root: Path,
        mutate,
        *,
        plugin_source: Path = PLUGIN_ROOT,
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        codex_home = root / "codex-home"
        cache_root = (
            codex_home / "plugins/cache/alive-private-alpha/alive/3.3.0-alpha.3"
        )
        copy_release_contents(plugin_source, cache_root)
        mutate(cache_root)
        result = subprocess.run(
            [
                "bash",
                str(PLUGIN_ROOT / "doctor.sh"),
                "--codex-bin",
                "/usr/bin/true",
                "--codex-home",
                str(codex_home),
                "--skip-mcp-setup",
                "--json",
            ],
            text=True,
            capture_output=True,
            timeout=15,
        )
        self.assertNotEqual("", result.stdout, result.stderr)
        return result, json.loads(result.stdout)

    def diagnose_installed_copy(
        self, root: Path, mutate
    ) -> tuple[subprocess.CompletedProcess[str], dict]:
        result, diagnosis = self.diagnose_copy(root, mutate)
        boundary = next(
            check
            for check in diagnosis["checks"]
            if check["name"] == "index_injection_boundary"
        )
        return result, boundary

    def test_plugin_is_self_contained_private_alpha(self) -> None:
        self.assertEqual([], plugin_errors(PLUGIN_ROOT))

    def test_world_skill_does_not_claim_full_index_is_injected(self) -> None:
        text = (PLUGIN_ROOT / "skills/alive-world/SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("Read the injected `<WORLD_INDEX>`", text)
        self.assertIn("_orientation.json", text)
        self.assertIn("_index.json", text)

    def test_world_skill_uses_the_index_stats_stash_field(self) -> None:
        text = (PLUGIN_ROOT / "skills/alive-world/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("stats.unsigned_with_stash", text)
        self.assertNotIn("unsaved_with_stash", text)

    def test_save_skill_explicitly_refreshes_and_verifies_orientation(self) -> None:
        text = (PLUGIN_ROOT / "skills/alive-save/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("save-refresh.py", text)
        self.assertIn('"$PLUGIN_ROOT/scripts/save-refresh.py" --world "$WORLD_ROOT"', text)
        self.assertIn("project.py --walnut", text)
        self.assertIn("generate-index.py WORLD_ROOT", text)
        self.assertIn("_orientation.json", text)
        self.assertIn("save is not fully complete", text)

    def test_package_contains_orientation_runtime(self) -> None:
        self.assertTrue((PLUGIN_ROOT / "scripts/orientation.py").is_file())

    def test_doctor_requires_each_orientation_refresh_runtime_file(self) -> None:
        """An installed cache missing any refresh dependency must fail doctor."""
        for missing in (
            "scripts/generate-index.py",
            "scripts/orientation.py",
            "scripts/save-refresh.py",
        ):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                result, diagnosis = self.diagnose_copy(
                    root, lambda cache, missing=missing: cache.joinpath(missing).unlink()
                )
                check = next(
                    item for item in diagnosis["checks"]
                    if item["name"] == "shared_runtime"
                )
                self.assertNotEqual(0, result.returncode)
                self.assertEqual("fail", check["status"])
                self.assertIn(missing, check["detail"])

    def test_doctor_reports_world_index_and_orientation_integrity(self) -> None:
        """A stale or invalid cache must be actionable instead of silently trusted."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / "codex-home"
            cache_root = (
                codex_home
                / "plugins/cache/alive-private-alpha/alive/3.3.0-alpha.3"
            )
            cache_root.parent.mkdir(parents=True)
            cache_root.symlink_to(PLUGIN_ROOT, target_is_directory=True)
            world = root / "world"
            alive = world / ".alive"
            alive.mkdir(parents=True)
            generated = subprocess.run(
                [
                    sys.executable,
                    str(PLUGIN_ROOT / "scripts" / "generate-index.py"),
                    str(world),
                ],
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(0, generated.returncode, generated.stderr)
            built = subprocess.run(
                [
                    sys.executable,
                    str(PLUGIN_ROOT / "scripts" / "orientation.py"),
                    "build",
                    str(world),
                ],
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(0, built.returncode, built.stderr)
            index = alive / "_index.json"
            orientation = alive / "_orientation.json"

            def diagnose() -> tuple[subprocess.CompletedProcess[str], dict]:
                result = subprocess.run(
                    [
                        "bash",
                        str(PLUGIN_ROOT / "doctor.sh"),
                        "--codex-bin",
                        "/usr/bin/true",
                        "--codex-home",
                        str(codex_home),
                        "--skip-mcp-setup",
                        "--json",
                        "--world",
                        str(world),
                    ],
                    text=True,
                    capture_output=True,
                    timeout=15,
                )
                self.assertNotEqual("", result.stdout, result.stderr)
                return result, json.loads(result.stdout)

            def check(name: str) -> tuple[subprocess.CompletedProcess[str], dict]:
                result, diagnosis = diagnose()
                return result, next(
                    check
                    for check in diagnosis["checks"]
                    if check["name"] == name
                )

            valid_result, valid_cache = check("world_orientation_cache")
            self.assertEqual(0, valid_result.returncode, valid_result.stderr)
            self.assertEqual("pass", valid_cache["status"])
            _, injection_boundary = check("index_injection_boundary")
            self.assertEqual("pass", injection_boundary["status"])

            index.write_text("{not json", encoding="utf-8")
            malformed_result, malformed = check("world_orientation_cache")
            self.assertNotEqual(0, malformed_result.returncode)
            self.assertEqual("fail", malformed["status"])
            self.assertIn("strict", malformed["detail"])

            generated = subprocess.run(
                [
                    sys.executable,
                    str(PLUGIN_ROOT / "scripts" / "generate-index.py"),
                    str(world),
                ],
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(0, generated.returncode, generated.stderr)
            orientation.write_bytes(b"{" + b" " * 8192 + b"}")
            oversized_result, oversized = check("world_orientation_cache")
            self.assertNotEqual(0, oversized_result.returncode)
            self.assertEqual("fail", oversized["status"])
            self.assertIn("_orientation.json exceeds 8192 bytes", oversized["detail"])

            orientation.write_text(
                '{"schema_version":2,"health":{},"counts":{},"recommendations":[]}',
                encoding="utf-8",
            )
            unsupported_result, unsupported = check("world_orientation_cache")
            self.assertNotEqual(0, unsupported_result.returncode)
            self.assertEqual("fail", unsupported["status"])
            self.assertIn("strict", unsupported["detail"])

            orientation.write_text(
                '{"schema_version":1,"health":{},"counts":{},"recommendations":[]}',
                encoding="utf-8",
            )
            os.utime(orientation, (1, 1))
            os.utime(index, (2, 2))
            stale_result, stale = check("world_orientation_cache")
            self.assertNotEqual(0, stale_result.returncode)
            self.assertEqual("fail", stale["status"])
            self.assertIn("strict", stale["detail"])

            orientation.write_text(
                '{"schema_version":true,"health":{},"counts":{},"recommendations":[]}',
                encoding="utf-8",
            )
            bool_schema_result, bool_schema = check("world_orientation_cache")
            self.assertNotEqual(0, bool_schema_result.returncode)
            self.assertEqual("fail", bool_schema["status"])
            self.assertIn("strict", bool_schema["detail"])

    def test_doctor_rejects_general_full_index_startup_claims(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            codex_home = root / "codex-home"
            cache_root = (
                codex_home
                / "plugins/cache/alive-private-alpha/alive/3.3.0-alpha.3"
            )
            shutil.copytree(PLUGIN_ROOT, cache_root)
            legacy = cache_root / "skills" / "legacy-claim"
            legacy.mkdir()
            legacy.joinpath("SKILL.md").write_text(
                "At startup, load the full world index from the hook injection.\n",
                encoding="utf-8",
            )
            direct_read = cache_root / "skills" / "direct-hook-read"
            direct_read.mkdir()
            direct_read.joinpath("SKILL.md").write_text(
                "The SessionStart hook reads .alive/_index.json.\n",
                encoding="utf-8",
            )
            truthful = cache_root / "skills" / "truthful-negative"
            truthful.mkdir()
            truthful.joinpath("SKILL.md").write_text(
                "Do not load the full world index from startup injection.\n",
                encoding="utf-8",
            )
            legacy_hook = cache_root / "hooks" / "scripts" / "legacy-index-read.sh"
            legacy_hook.write_text(
                'cat "$WORLD_ROOT/.alive/_index.yaml"\n', encoding="utf-8"
            )
            context_watch = (
                cache_root / "hooks" / "scripts" / "alive-context-watch.sh"
            )
            context_watch.write_text(
                context_watch.read_text(encoding="utf-8")
                + '\nsource "$SCRIPT_DIR/legacy-index-read.sh"\n',
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    "bash",
                    str(PLUGIN_ROOT / "doctor.sh"),
                    "--codex-bin",
                    "/usr/bin/true",
                    "--codex-home",
                    str(codex_home),
                    "--skip-mcp-setup",
                    "--json",
                ],
                text=True,
                capture_output=True,
                timeout=15,
            )
            diagnosis = json.loads(result.stdout)
            boundary = next(
                check
                for check in diagnosis["checks"]
                if check["name"] == "index_injection_boundary"
            )
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("fail", boundary["status"])
            self.assertIn("legacy-claim/SKILL.md", boundary["detail"])
            self.assertIn("direct-hook-read/SKILL.md", boundary["detail"])
            self.assertIn("hooks/scripts/legacy-index-read.sh", boundary["detail"])
            self.assertNotIn("truthful-negative/SKILL.md", boundary["detail"])

    def test_doctor_rejects_index_reads_in_registered_hook_dependencies(self) -> None:
        """Dropping any direct-read detector would let a registered prompt path load an index."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def mutate(cache_root: Path) -> None:
                scripts = cache_root / "hooks" / "scripts"
                context_watch = scripts / "alive-context-watch.sh"
                context_watch.write_text(
                    context_watch.read_text(encoding="utf-8")
                    + '\nsource "$SCRIPT_DIR/read-pathlib.sh"\n'
                    + 'source "$SCRIPT_DIR/read-head.sh"\n'
                    + 'source "$SCRIPT_DIR/read-jq.sh"\n'
                    + 'source "$SCRIPT_DIR/read-sed.sh"\n'
                    + 'source "$SCRIPT_DIR/read-redirect.sh"\n'
                    + 'source "$SCRIPT_DIR/read-variable.sh"\n'
                    + 'source "${SCRIPT_DIR}/read-braced-script-dir.sh"\n'
                    + 'source "$PLUGIN_ROOT/hooks/scripts/read-plugin-path.sh"\n'
                    + 'source "${PLUGIN_ROOT}/hooks/scripts/read-braced-plugin-path.sh"\n',
                    encoding="utf-8",
                )
                fixtures = {
                    "read-pathlib.sh": (
                        "python3 -c 'from pathlib import Path; "
                        'Path(\".alive/_index.json\").read_text()\'\n'
                    ),
                    "read-head.sh": 'head -n 1 "$WORLD_ROOT/.alive/_index.yaml"\n',
                    "read-jq.sh": 'jq . "$WORLD_ROOT/.alive/_index.json"\n',
                    "read-sed.sh": 'sed -n "1p" "$WORLD_ROOT/.alive/_index.yaml"\n',
                    "read-redirect.sh": (
                        'INDEX_CONTENT=$(< "$WORLD_ROOT/.alive/_index.json")\n'
                    ),
                    "read-variable.sh": (
                        'INDEX_PATH="$WORLD_ROOT/.alive/_index.yaml"\n'
                        'cat "$INDEX_PATH"\n'
                    ),
                    "read-braced-script-dir.sh": (
                        'cat "$WORLD_ROOT/.alive/_index.json"\n'
                    ),
                    "read-plugin-path.sh": (
                        'head -n 1 "$WORLD_ROOT/.alive/_index.yaml"\n'
                    ),
                    "read-braced-plugin-path.sh": (
                        'jq . "$WORLD_ROOT/.alive/_index.json"\n'
                    ),
                }
                for name, content in fixtures.items():
                    scripts.joinpath(name).write_text(content, encoding="utf-8")

            result, boundary = self.diagnose_installed_copy(root, mutate)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("fail", boundary["status"])
            for name in (
                "read-pathlib.sh",
                "read-head.sh",
                "read-jq.sh",
                "read-sed.sh",
                "read-redirect.sh",
                "read-variable.sh",
                "read-braced-script-dir.sh",
                "read-plugin-path.sh",
                "read-braced-plugin-path.sh",
            ):
                self.assertIn(f"hooks/scripts/{name}", boundary["detail"])

    def test_doctor_follows_split_quoted_registered_hook_dependencies(self) -> None:
        """A quote boundary in a source path must not hide lifecycle index reads."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def mutate(cache_root: Path) -> None:
                scripts = cache_root / "hooks" / "scripts"
                context_watch = scripts / "alive-context-watch.sh"
                context_watch.write_text(
                    context_watch.read_text(encoding="utf-8")
                    + '\nsource "$SCRIPT_DIR"/split-script-dir-json.sh\n'
                    + 'source "${SCRIPT_DIR}"/split-braced-script-dir-yaml.sh\n'
                    + 'source "$PLUGIN_ROOT/hooks/scripts"/split-plugin-path-json.sh\n'
                    + 'source "${PLUGIN_ROOT}/hooks/scripts"/split-braced-plugin-path-yaml.sh\n'
                    + 'source "$PLUGIN_ROOT"/hooks/scripts/split-plugin-root-json.sh\n'
                    + 'source "${PLUGIN_ROOT}"/hooks/scripts/split-braced-plugin-root-yaml.sh\n',
                    encoding="utf-8",
                )
                fixtures = {
                    "split-script-dir-json.sh": (
                        'jq . "$WORLD_ROOT/.alive/_index.json"\n'
                    ),
                    "split-braced-script-dir-yaml.sh": (
                        'cat "$WORLD_ROOT/.alive/_index.yaml"\n'
                    ),
                    "split-plugin-path-json.sh": (
                        'cat "$WORLD_ROOT/.alive/_index.json"\n'
                    ),
                    "split-braced-plugin-path-yaml.sh": (
                        'head -n 1 "$WORLD_ROOT/.alive/_index.yaml"\n'
                    ),
                    "split-plugin-root-json.sh": (
                        'sed -n "1p" "$WORLD_ROOT/.alive/_index.json"\n'
                    ),
                    "split-braced-plugin-root-yaml.sh": (
                        'jq . "$WORLD_ROOT/.alive/_index.yaml"\n'
                    ),
                }
                for name, content in fixtures.items():
                    scripts.joinpath(name).write_text(content, encoding="utf-8")

            result, boundary = self.diagnose_installed_copy(root, mutate)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("fail", boundary["status"])
            for name in (
                "split-script-dir-json.sh",
                "split-braced-script-dir-yaml.sh",
                "split-plugin-path-json.sh",
                "split-braced-plugin-path-yaml.sh",
                "split-plugin-root-json.sh",
                "split-braced-plugin-root-yaml.sh",
            ):
                self.assertIn(f"hooks/scripts/{name}", boundary["detail"])

    def test_doctor_allows_dormant_hook_reads_and_on_demand_skill_usage(self) -> None:
        """Scanning every shell file or skill code would reject non-lifecycle retrieval."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def mutate(cache_root: Path) -> None:
                dormant = cache_root / "hooks" / "scripts" / "dormant-reader.sh"
                dormant.write_text(
                    'cat "$WORLD_ROOT/.alive/_index.yaml"\n', encoding="utf-8"
                )
                skill = cache_root / "skills" / "on-demand-index"
                skill.mkdir()
                skill.joinpath("SKILL.md").write_text(
                    "When explicitly invoked for search, run "
                    "`jq . \"$WORLD_ROOT/.alive/_index.json\"`.\n",
                    encoding="utf-8",
                )

            result, boundary = self.diagnose_installed_copy(root, mutate)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual("pass", boundary["status"])
            self.assertNotIn("dormant-reader.sh", boundary["detail"])
            self.assertNotIn("on-demand-index", boundary["detail"])

    def test_diagnostic_copy_excludes_development_dependencies(self) -> None:
        """Installed-copy checks must model release contents, even in a dev checkout."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source_root = root / "source-plugin"
            shutil.copytree(
                PLUGIN_ROOT,
                source_root,
                ignore=shutil.ignore_patterns(
                    ".venv", "node_modules", ".pytest_cache", "__pycache__", "dist"
                ),
            )
            for relative in (
                "mcp/.venv/bin",
                "mcp/node_modules/example",
                ".pytest_cache",
                "scripts/__pycache__",
                "dist",
            ):
                source_root.joinpath(relative).mkdir(parents=True, exist_ok=True)
            source_root.joinpath("mcp", ".venv", "bin", "python").write_text(
                "#!/bin/sh\nexit 17\n", encoding="utf-8"
            )
            source_root.joinpath("mcp", ".venv", "bin", "python").chmod(0o755)

            def assert_release_copy(cache_root: Path) -> None:
                for relative in (
                    "mcp/.venv",
                    "mcp/node_modules",
                    ".pytest_cache",
                    "scripts/__pycache__",
                    "dist",
                ):
                    self.assertFalse(cache_root.joinpath(relative).exists(), relative)

            result, diagnosis = self.diagnose_copy(
                root,
                assert_release_copy,
                plugin_source=source_root,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            mcp = next(
                check for check in diagnosis["checks"]
                if check["name"] == "mcp_environment"
            )
            self.assertEqual("warn", mcp["status"])

    def test_doctor_rejects_broken_installed_mcp_environment(self) -> None:
        """Release-copy exclusions must not weaken doctor for an installed bad env."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def install_broken_environment(cache_root: Path) -> None:
                python = cache_root / "mcp" / ".venv" / "bin" / "python"
                python.parent.mkdir(parents=True)
                python.write_text("#!/bin/sh\nexit 17\n", encoding="utf-8")
                python.chmod(0o755)

            result, diagnosis = self.diagnose_copy(
                root, install_broken_environment
            )
            self.assertNotEqual(0, result.returncode)
            mcp = next(
                check for check in diagnosis["checks"]
                if check["name"] == "mcp_environment"
            )
            self.assertEqual("fail", mcp["status"])
            self.assertIn("imports fail", mcp["detail"])

    def test_doctor_follows_executed_packaged_python_and_shell_helpers(self) -> None:
        """A registered hook cannot hide an index read behind an executed helper."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def mutate(cache_root: Path) -> None:
                start = cache_root / "hooks" / "scripts" / "alive-session-start.sh"
                start.write_text(
                    start.read_text(encoding="utf-8")
                    + '\nPY_HELPER="$PLUGIN_ROOT/scripts/runtime-index-reader.py"\n'
                    + 'SH_HELPER="$PLUGIN_ROOT/scripts/runtime-index-reader.sh"\n'
                    + 'python3 "$PY_HELPER"\n'
                    + 'bash "$SH_HELPER"\n',
                    encoding="utf-8",
                )
                cache_root.joinpath("scripts", "runtime-index-reader.py").write_text(
                    "import subprocess, sys\n"
                    "from pathlib import Path\n"
                    'subprocess.run([sys.executable, str(Path(__file__).with_name("nested-index-reader.py"))])\n',
                    encoding="utf-8",
                )
                cache_root.joinpath("scripts", "nested-index-reader.py").write_text(
                    'from pathlib import Path\n'
                    'Path(".alive/_index.json").read_text(encoding="utf-8")\n',
                    encoding="utf-8",
                )
                cache_root.joinpath("scripts", "runtime-index-reader.sh").write_text(
                    'head -n 1 "$WORLD_ROOT/.alive/_index.yaml"\n',
                    encoding="utf-8",
                )

            result, boundary = self.diagnose_installed_copy(root, mutate)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("fail", boundary["status"])
            self.assertIn("scripts/nested-index-reader.py", boundary["detail"])
            self.assertIn("scripts/runtime-index-reader.sh", boundary["detail"])


if __name__ == "__main__":
    unittest.main()
