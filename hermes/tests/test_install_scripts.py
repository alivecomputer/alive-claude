"""Offline tests for hermes/setup-crons.sh and hermes/install.sh.

No Hermes installation is required: a stub ``hermes`` executable on a
controlled PATH stands in for the real CLI and records every invocation.

Run with:  python3 -m pytest hermes/tests/test_install_scripts.py -q
"""

import re
import subprocess
from pathlib import Path

import pytest

HERMES_DIR = Path(__file__).resolve().parents[1]
SETUP_CRONS = HERMES_DIR / "setup-crons.sh"
INSTALL = HERMES_DIR / "install.sh"

# Fields in stub invocation logs are separated by the ASCII unit separator.
SEP = "\x1f"

STUB = """#!/usr/bin/env bash
# hermes CLI test double: records invocations, behavior scripted via env.
set -u
if [ -n "${HERMES_STUB_LOG:-}" ]; then
  { printf '%s\\x1f' "$@"; printf '\\n'; } >> "$HERMES_STUB_LOG"
fi
case "${1:-} ${2:-}" in
  "cron create")
    if [ -n "${HERMES_STUB_FAIL_NAME:-}" ]; then
      for arg in "$@"; do
        if [ "$arg" = "$HERMES_STUB_FAIL_NAME" ]; then
          echo "stub: simulated cron create failure" >&2
          exit 1
        fi
      done
    fi
    ;;
  "plugins list")
    printf '%s\\n' "${HERMES_STUB_PLUGINS_OUTPUT-alive    memory-provider    enabled}"
    ;;
  "memory status")
    printf '%s\\n' "${HERMES_STUB_MEMORY_OUTPUT-active provider: none}"
    ;;
esac
exit 0
"""

CORE_SKILLS = [
    "alive-morning",
    "alive-project",
    "alive-inbox",
    "alive-stash-router",
    "alive-mine",
]
OPTIONAL_SKILLS = ["alive-health", "alive-prune", "alive-people"]
ALWAYS_LOCAL_SKILLS = ["alive-project", "alive-mine"]


@pytest.fixture
def env(tmp_path):
    """Isolated HOME/HERMES_HOME and a controlled PATH with the hermes stub."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "hermes"
    stub.write_text(STUB)
    stub.chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    log = tmp_path / "hermes-stub.log"
    return {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "HOME": str(home),
        "HERMES_HOME": str(home / ".hermes"),
        "HERMES_STUB_LOG": str(log),
    }


def run(script, *args, env, check=False):
    result = subprocess.run(
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        stdin=subprocess.DEVNULL,
        timeout=60,
    )
    if check:
        assert result.returncode == 0, (
            f"{script.name} {' '.join(args)} failed "
            f"(rc={result.returncode})\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def stub_calls(env):
    """Parse the stub log into a list of argv lists."""
    log = Path(env["HERMES_STUB_LOG"])
    if not log.exists():
        return []
    calls = []
    for line in log.read_text().splitlines():
        if line:
            calls.append(line.split(SEP)[:-1])
    return calls


# ── setup-crons.sh ───────────────────────────────────────────────


class TestSetupCronsDryRun:
    def test_prints_eight_positional_commands(self, env):
        result = run(SETUP_CRONS, env=env, check=True)
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 8
        # Positional: schedule then prompt, then only supported flags.
        pattern = re.compile(
            r"^hermes cron create '[^']+' '[^']+' "
            r"--name '[^']+' --skill '[^']+' --deliver '[^']+'$"
        )
        for line in lines:
            assert pattern.match(line), f"malformed command: {line}"
        assert "--schedule" not in result.stdout
        assert "--prompt" not in result.stdout

    def test_executes_nothing(self, env):
        run(SETUP_CRONS, env=env, check=True)
        assert stub_calls(env) == []

    def test_covers_all_eight_skills(self, env):
        result = run(SETUP_CRONS, env=env, check=True)
        for skill in CORE_SKILLS + OPTIONAL_SKILLS:
            assert f"--skill '{skill}'" in result.stdout

    def test_core_only_skips_the_three_optional_jobs(self, env):
        result = run(SETUP_CRONS, "--core-only", env=env, check=True)
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 5
        for skill in CORE_SKILLS:
            assert f"--skill '{skill}'" in result.stdout
        for skill in OPTIONAL_SKILLS:
            assert skill not in result.stdout

    def test_deliver_local_is_the_default(self, env):
        result = run(SETUP_CRONS, env=env, check=True)
        for line in result.stdout.strip().splitlines():
            assert "--deliver 'local'" in line

    def test_deliver_flag_spares_maintenance_jobs(self, env):
        result = run(SETUP_CRONS, "--deliver", "telegram", env=env, check=True)
        for line in result.stdout.strip().splitlines():
            skill = re.search(r"--skill '([^']+)'", line).group(1)
            expected = "local" if skill in ALWAYS_LOCAL_SKILLS else "telegram"
            assert f"--deliver '{expected}'" in line, line

    def test_unknown_argument_is_an_error(self, env):
        result = run(SETUP_CRONS, "--bogus", env=env)
        assert result.returncode != 0


class TestSetupCronsApply:
    def test_apply_invokes_hermes_eight_times_positionally(self, env):
        run(SETUP_CRONS, "--apply", env=env, check=True)
        calls = stub_calls(env)
        creates = [c for c in calls if c[:2] == ["cron", "create"]]
        assert len(creates) == 8
        for argv in creates:
            # argv[2] = schedule, argv[3] = prompt — both positional.
            assert re.match(r"^(\d+ [\d*]+ \* \* [\d*,]+|every \d+h)$", argv[2]), argv
            assert argv[3].startswith("Run the alive-"), argv
            assert "--schedule" not in argv
            assert "--prompt" not in argv
            for flag in ("--name", "--skill", "--deliver"):
                assert flag in argv, argv

    def test_failed_create_exits_nonzero_and_names_the_job(self, env):
        env = dict(env, HERMES_STUB_FAIL_NAME="ALIVE Inbox Scanner")
        result = run(SETUP_CRONS, "--apply", env=env)
        assert result.returncode != 0
        assert "ALIVE Inbox Scanner" in result.stderr
        # Third job fails -> the run stops there, later jobs are not attempted.
        creates = [c for c in stub_calls(env) if c[:2] == ["cron", "create"]]
        assert len(creates) == 3


# ── install.sh ───────────────────────────────────────────────────


PROVIDER_FILES = ["__init__.py", "plugin.yaml", "README.md"]


def provider_dir(env):
    return Path(env["HERMES_HOME"]) / "plugins" / "memory" / "alive"


def tree_snapshot(root):
    return sorted(
        (str(p.relative_to(root)), p.stat().st_size)
        for p in Path(root).rglob("*")
        if p.is_file()
    )


class TestInstall:
    def test_installs_provider_to_user_plugin_dir(self, env):
        result = run(INSTALL, env=env, check=True)
        for f in PROVIDER_FILES:
            assert (provider_dir(env) / f).is_file()
        # Never the repo-checkout layout.
        assert not (Path(env["HERMES_HOME"]) / "hermes-agent").exists()
        assert "plugins/memory/alive" in result.stdout

    def test_prints_the_env_contract(self, env):
        result = run(INSTALL, env=env, check=True)
        assert "ALIVE_WORLD_ROOT" in result.stdout
        assert "ALIVE_PLUGIN_ROOT" in result.stdout

    def test_without_hermes_binary_warns_and_still_succeeds(self, env):
        env = dict(env, PATH="/usr/bin:/bin")  # no stub on PATH
        result = run(INSTALL, env=env, check=True)
        assert "hermes binary not found" in result.stdout
        assert "hermes plugins list" in result.stdout  # how to verify later
        for f in PROVIDER_FILES:
            assert (provider_dir(env) / f).is_file()

    def test_idempotent_rerun_converges(self, env):
        hermes_home = Path(env["HERMES_HOME"])
        hermes_home.mkdir(parents=True)
        (hermes_home / "config.yaml").write_text("model: something\n")
        (hermes_home / "SOUL.md").write_text("# Soul\n")

        run(INSTALL, env=env, check=True)
        first = tree_snapshot(hermes_home)
        run(INSTALL, env=env, check=True)
        second = tree_snapshot(hermes_home)
        assert first == second

        # Guarded appends happened exactly once.
        config = (hermes_home / "config.yaml").read_text()
        assert config.count("external_dirs") == 1
        soul = (hermes_home / "SOUL.md").read_text()
        assert soul.count("squirrel") == 1

    def test_verification_passes_when_plugin_listed(self, env):
        result = run(INSTALL, env=env, check=True)
        assert "reports the alive plugin" in result.stdout
        # The stub was actually asked.
        assert ["plugins", "list"] in stub_calls(env)

    def test_verification_fails_loudly_when_plugin_not_listed(self, env):
        env = dict(env, HERMES_STUB_PLUGINS_OUTPUT="mem0    memory-provider    enabled")
        result = run(INSTALL, env=env)
        assert result.returncode != 0
        assert "does not show the alive plugin" in result.stdout
        assert "verification failed" in result.stderr

    def test_no_world_scaffold_unless_requested(self, env):
        run(INSTALL, env=env, check=True)
        assert not (Path(env["HOME"]) / "world").exists()

    def test_scaffold_world_flag_creates_world(self, env):
        result = run(INSTALL, "--scaffold-world", env=env, check=True)
        world = Path(env["HOME"]) / "world"
        assert (world / ".alive" / "key.md").is_file()
        assert (world / ".alive" / "preferences.yaml").is_file()
        assert "World created" in result.stdout
        # And the env contract now points at it.
        assert f"ALIVE_WORLD_ROOT={world}" in result.stdout
