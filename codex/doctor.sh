#!/usr/bin/env bash
set -euo pipefail

plugin_source="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$plugin_source/lib/codex-plugin.sh"
alive_parse_args "$@"
mkdir -p "$ALIVE_CODEX_HOME"

plugin_root=$(alive_find_plugin_root 2>/dev/null || true)
codex_status="fail"
codex_detail="Codex executable did not run"
if [ -x "${ALIVE_CODEX_BIN:-}" ] && codex_detail=$("$ALIVE_CODEX_BIN" --version 2>&1); then
  codex_status="pass"
fi

manifest_status="fail"
manifest_detail="Installed manifest is missing or does not satisfy the current Codex ingestion contract."
if [ -n "$plugin_root" ] && ALIVE_MANIFEST="$plugin_root/.codex-plugin/plugin.json" python3 -c '
import json, os, pathlib
path = pathlib.Path(os.environ["ALIVE_MANIFEST"])
try:
    manifest = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit(1)
capabilities = manifest.get("interface", {}).get("capabilities")
valid = (
    manifest.get("version") == "3.3.0-alpha.3"
    and manifest.get("skills") == "./skills/"
    and manifest.get("mcpServers") == "./.mcp.json"
    and "hooks" not in manifest
    and isinstance(capabilities, list)
    and all(isinstance(value, str) and value.strip() for value in capabilities)
)
raise SystemExit(0 if valid else 1)
' 2>/dev/null; then
  manifest_status="pass"
  manifest_detail="Installed manifest satisfies the current Codex ingestion contract."
fi

hooks_status="fail"
if [ -n "$plugin_root" ] && [ -f "$plugin_root/hooks/hooks.json" ] && \
   grep -q 'exec_command' "$plugin_root/hooks/hooks.json"; then
  hooks_status="pass"
fi

conflicts_status="pass"
conflicts_detail="No second enabled ALIVE product was found."
if conflict_output=$(alive_require_single_alive_product 2>&1); then
  :
else
  conflicts_status="fail"
  conflicts_detail="$conflict_output"
fi

runtime_status="fail"
runtime_detail="Installed plugin root is missing."
runtime_missing=""
if [ -n "$plugin_root" ]; then
  for required_runtime in \
    scripts/project.py \
    scripts/tasks.py \
    scripts/generate-index.py \
    scripts/orientation.py \
    scripts/save-refresh.py; do
    if [ ! -f "$plugin_root/$required_runtime" ]; then
      runtime_missing="${runtime_missing}${runtime_missing:+, }${required_runtime}"
    fi
  done
  if [ ! -d "$plugin_root/templates" ]; then
    runtime_missing="${runtime_missing}${runtime_missing:+, }templates/"
  fi
fi
if [ -n "$plugin_root" ] && [ -z "$runtime_missing" ]; then
  runtime_status="pass"
  runtime_detail="Projection, index, orientation, save verification, task, and template runtimes are packaged."
elif [ -n "$plugin_root" ]; then
  runtime_detail="Missing installed runtime dependency: $runtime_missing"
fi

orientation_status="warn"
orientation_detail="No --world path was supplied; world index and orientation cache were not inspected."
if [ -n "${ALIVE_WORLD_ROOT:-}" ]; then
  if [ -d "$ALIVE_WORLD_ROOT/.alive" ]; then
    index_path="$ALIVE_WORLD_ROOT/.alive/_index.json"
    orientation_path="$ALIVE_WORLD_ROOT/.alive/_orientation.json"
    if [ ! -f "$index_path" ]; then
      orientation_result="fail|_index.json is missing; strict orientation identity cannot be verified"
    elif [ ! -f "$orientation_path" ]; then
      orientation_result="fail|_orientation.json is missing"
    elif [ "$(wc -c < "$orientation_path" | tr -d '[:space:]')" -gt 8192 ] 2>/dev/null; then
      orientation_result="fail|_orientation.json exceeds 8192 bytes"
    elif [ -z "$plugin_root" ] || [ ! -f "$plugin_root/scripts/orientation.py" ]; then
      orientation_result="fail|strict orientation validator is missing from the installed plugin"
    elif validation_output=$(python3 "$plugin_root/scripts/orientation.py" validate \
      "$ALIVE_WORLD_ROOT" --identity-mode digest 2>&1); then
      orientation_result="pass|Strict schema-1 and full index identity validation passed."
    else
      validation_output=$(printf '%s' "$validation_output" | tr '\n' ' ' | cut -c1-360)
      orientation_result="fail|Strict schema-1 or index identity validation failed: $validation_output"
    fi
    orientation_status="${orientation_result%%|*}"
    orientation_detail="${orientation_result#*|}"
  else
    orientation_status="fail"
    orientation_detail="ALIVE_WORLD_ROOT is not an ALIVE world: $ALIVE_WORLD_ROOT"
  fi
fi

injection_status="fail"
injection_detail="Installed plugin root is missing; package skills could not be checked."
if [ -n "$plugin_root" ]; then
injection_result=$(ALIVE_SKILLS_ROOT="$plugin_root/skills" python3 -c '
import json, os, re
from pathlib import Path

skills = Path(os.environ["ALIVE_SKILLS_ROOT"])
legacy = []
claim_patterns = (
    re.compile(r"\b(?:startup|sessionstart|hook|injection)\b.{0,180}?\b(?:read|load|inject|receive|surface)\b.{0,180}?\b(?:full\s+)?(?:world\s+)?index\b", re.I),
    re.compile(r"\b(?:read|load|inject|receive|surface)\b.{0,180}?\b(?:full\s+)?(?:world\s+)?index\b.{0,180}?\b(?:startup|sessionstart|hook|injection)\b", re.I),
    re.compile(r"\b(?:startup|sessionstart|hook)\b.{0,180}?\b(?:cat|cats|read|reads|load|loads)\b.{0,180}?_index\.(?:json|yaml)\b", re.I),
    re.compile(r"\b(?:cat|cats|read|reads|load|loads)\b.{0,180}?_index\.(?:json|yaml)\b.{0,180}?\b(?:startup|sessionstart|hook)\b", re.I),
)
negative = re.compile(r"\b(?:do not|dont|does not|not|never|rather than|without)\b", re.I)
for path in sorted(skills.rglob("SKILL.md")):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    fragments = re.split(r"(?<=[.!?])\s+|\n", text)
    positive_claim = any(
        ("<WORLD_INDEX>" in fragment or any(pattern.search(fragment) for pattern in claim_patterns))
        and not negative.search(fragment)
        for fragment in fragments
    )
    if positive_claim:
        legacy.append(path.relative_to(skills).as_posix())
if legacy:
    skill_detail = "package skill still claims the full index is injected: " + ", ".join(legacy)
else:
    skill_detail = "package skills do not claim that the full world index is injected"
hook_root = skills.parent / "hooks" / "scripts"
hook_legacy = []
hooks_config = skills.parent / "hooks" / "hooks.json"
registered = set()
try:
    hooks_payload = json.loads(hooks_config.read_text(encoding="utf-8"))
except (OSError, UnicodeDecodeError, json.JSONDecodeError):
    hooks_payload = {}
for event in ("SessionStart", "UserPromptSubmit"):
    for group in hooks_payload.get("hooks", {}).get(event, []):
        for hook in group.get("hooks", []):
            command = hook.get("command", "")
            if not isinstance(command, str):
                continue
            registered.update(
                "hooks/scripts/" + name
                for name in re.findall(r"hooks/scripts/([A-Za-z0-9._-]+\.sh)", command)
            )

def normalized_shell(text):
    return (
        text.replace("\"", "")
        .replace("\x27", "")
        .replace("${SCRIPT_DIR}", "$SCRIPT_DIR")
        .replace("${PLUGIN_ROOT}", "$PLUGIN_ROOT")
    )

def dependencies(relative, text):
    found = set()
    normalized = normalized_shell(text)
    assignments = {}
    for line in normalized.splitlines():
        assigned = re.match(
            r"^\s*(?:local\s+)?([A-Za-z_][A-Za-z0-9_]*)="
            r"(\$PLUGIN_ROOT/scripts/[A-Za-z0-9._-]+\.(?:py|sh))\s*$",
            line,
        )
        if assigned:
            assignments[assigned.group(1)] = assigned.group(2)
    if relative.startswith("hooks/scripts/"):
        for line in normalized.splitlines():
            if re.match(r"^\s*(?:source|\.)\s+", line):
                found.update(
                    "hooks/scripts/" + name
                    for name in re.findall(
                        r"(?:\$SCRIPT_DIR/|\$PLUGIN_ROOT/hooks/scripts/)"
                        r"([A-Za-z0-9._-]+\.sh)",
                        line,
                    )
                )
            if re.search(r"^\s*(?:python3|python|bash|sh)\s+", line):
                found.update(
                    "scripts/" + name
                    for name in re.findall(
                        r"\$PLUGIN_ROOT/scripts/([A-Za-z0-9._-]+\.(?:py|sh))",
                        line,
                    )
                )
                for variable in re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", line):
                    assigned_path = assignments.get(variable, "")
                    matched = re.search(
                        r"\$PLUGIN_ROOT/scripts/([A-Za-z0-9._-]+\.(?:py|sh))",
                        assigned_path,
                    )
                    if matched:
                        found.add("scripts/" + matched.group(1))
                found.update(
                    "hooks/scripts/" + name
                    for name in re.findall(
                        r"(?:\$SCRIPT_DIR/|\$PLUGIN_ROOT/hooks/scripts/)"
                        r"([A-Za-z0-9._-]+\.sh)",
                        line,
                    )
                )
    elif relative.startswith("scripts/"):
        for line in normalized.splitlines():
            if re.search(r"^\s*(?:python3|python|bash|sh)\s+", line):
                found.update(
                    "scripts/" + name
                    for name in re.findall(
                        r"\$PLUGIN_ROOT/scripts/([A-Za-z0-9._-]+\.(?:py|sh))",
                        line,
                    )
                )
                for variable in re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", line):
                    assigned_path = assignments.get(variable, "")
                    matched = re.search(
                        r"\$PLUGIN_ROOT/scripts/([A-Za-z0-9._-]+\.(?:py|sh))",
                        assigned_path,
                    )
                    if matched:
                        found.add("scripts/" + matched.group(1))
        if relative.endswith(".py"):
            found.update(
                "scripts/" + name
                for name in re.findall(
                    r"[\x22\x27]([A-Za-z0-9._-]+\.(?:py|sh))[\x22\x27]",
                    text,
                )
            )
    return found

pending = list(registered)
hook_text = {}
while pending:
    relative = pending.pop()
    if relative in hook_text:
        continue
    path = skills.parent / relative
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    hook_text[relative] = text
    pending.extend(
        dependency
        for dependency in dependencies(relative, text)
        if dependency not in hook_text
    )

direct_read = re.compile(
    r"(?:"
    r"\b(?:cat|head|jq|sed)\b[^\n]*_index\.(?:json|yaml)"
    r"|_index\.(?:json|yaml)[^\n]*\.(?:read_text|read_bytes|open)\s*\("
    r"|\b(?:open|readFileSync)\s*\([^\n]*_index\.(?:json|yaml)"
    r"|<\s*[^\n]*_index\.(?:json|yaml)"
    r")",
    re.I,
)
assignment = re.compile(
    r"(?m)^\s*(?:local\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=[^\n]*_index\.(?:json|yaml)"
)
for relative, text in sorted(hook_text.items()):
    reads_index = bool(direct_read.search(text))
    for variable in assignment.findall(text):
        escaped = re.escape(variable)
        shell_reference = r"\$(?:\{" + escaped + r"\}|" + escaped + r")"
        variable_reads = (
            r"\b(?:cat|head|jq|sed)\b[^\n]*" + shell_reference,
            r"<\s*[^\n]*" + shell_reference,
            r"\b(?:open|readFileSync)\s*\(\s*" + escaped + r"\b",
            r"\b" + escaped + r"\.(?:read_text|read_bytes|open)\s*\(",
        )
        if any(re.search(pattern, text) for pattern in variable_reads):
            reads_index = True
            break
    if reads_index:
        hook_legacy.append(relative)
if legacy or hook_legacy:
    details = [detail for detail in (skill_detail if legacy else "", ", ".join(hook_legacy)) if detail]
    print("fail|" + "; direct hook index read: ".join(details))
else:
    print("pass|" + skill_detail + "; hooks do not read or inject full index files")
' 2>/dev/null || printf 'fail|package skill boundary validation could not run')
  injection_status="${injection_result%%|*}"
  injection_detail="${injection_result#*|}"
fi

mcp_status="warn"
mcp_detail="Locked MCP environment is not prepared; rerun install without --skip-mcp-setup."
if [ -n "$plugin_root" ] && [ -x "$plugin_root/mcp/.venv/bin/python" ]; then
  if PYTHONPATH="$plugin_root/mcp/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$plugin_root/mcp/.venv/bin/python" -c 'import alive_mcp, mcp, watchdog' >/dev/null 2>&1; then
    mcp_status="pass"
    mcp_detail="Locked read-only MCP environment imports successfully."
  else
    mcp_status="fail"
    mcp_detail="MCP environment exists but its imports fail."
  fi
fi

overall="pass"
for status in "$codex_status" "$manifest_status" "$hooks_status" "$conflicts_status" "$runtime_status" "$orientation_status" "$injection_status" "$mcp_status"; do
  if [ "$status" = "fail" ]; then overall="fail"; break; fi
  if [ "$status" = "warn" ]; then overall="warn"; fi
done

if [ "$ALIVE_JSON" = "1" ]; then
  ALIVE_DOCTOR_STATUS="$overall" ALIVE_DOCTOR_CODEX_STATUS="$codex_status" \
    ALIVE_DOCTOR_CODEX_DETAIL="$codex_detail" ALIVE_DOCTOR_MANIFEST="$manifest_status" \
    ALIVE_DOCTOR_MANIFEST_DETAIL="$manifest_detail" \
    ALIVE_DOCTOR_HOOKS="$hooks_status" ALIVE_DOCTOR_RUNTIME="$runtime_status" \
    ALIVE_DOCTOR_RUNTIME_DETAIL="$runtime_detail" \
    ALIVE_DOCTOR_ORIENTATION="$orientation_status" \
    ALIVE_DOCTOR_ORIENTATION_DETAIL="$orientation_detail" \
    ALIVE_DOCTOR_INDEX_INJECTION="$injection_status" \
    ALIVE_DOCTOR_INDEX_INJECTION_DETAIL="$injection_detail" \
    ALIVE_DOCTOR_CONFLICTS="$conflicts_status" \
    ALIVE_DOCTOR_CONFLICTS_DETAIL="$conflicts_detail" \
    ALIVE_DOCTOR_MCP="$mcp_status" ALIVE_DOCTOR_MCP_DETAIL="$mcp_detail" \
    ALIVE_DOCTOR_PLUGIN_ROOT="$plugin_root" python3 -c '
import json, os
checks = [
    {"name": "codex", "status": os.environ["ALIVE_DOCTOR_CODEX_STATUS"], "detail": os.environ["ALIVE_DOCTOR_CODEX_DETAIL"]},
    {"name": "plugin_manifest", "status": os.environ["ALIVE_DOCTOR_MANIFEST"], "detail": os.environ["ALIVE_DOCTOR_MANIFEST_DETAIL"]},
    {"name": "native_hooks", "status": os.environ["ALIVE_DOCTOR_HOOKS"], "detail": "Auto-discovered plugin hooks include current Codex tool aliases; trust remains user-controlled."},
    {"name": "alive_product_conflicts", "status": os.environ["ALIVE_DOCTOR_CONFLICTS"], "detail": os.environ["ALIVE_DOCTOR_CONFLICTS_DETAIL"]},
    {"name": "shared_runtime", "status": os.environ["ALIVE_DOCTOR_RUNTIME"], "detail": os.environ["ALIVE_DOCTOR_RUNTIME_DETAIL"]},
    {"name": "world_orientation_cache", "status": os.environ["ALIVE_DOCTOR_ORIENTATION"], "detail": os.environ["ALIVE_DOCTOR_ORIENTATION_DETAIL"]},
    {"name": "index_injection_boundary", "status": os.environ["ALIVE_DOCTOR_INDEX_INJECTION"], "detail": os.environ["ALIVE_DOCTOR_INDEX_INJECTION_DETAIL"]},
    {"name": "mcp_environment", "status": os.environ["ALIVE_DOCTOR_MCP"], "detail": os.environ["ALIVE_DOCTOR_MCP_DETAIL"]},
]
print(json.dumps({"status": os.environ["ALIVE_DOCTOR_STATUS"], "plugin_root": os.environ.get("ALIVE_DOCTOR_PLUGIN_ROOT", ""), "checks": checks}, sort_keys=True))
'
else
  printf 'ALIVE doctor: %s\n' "$overall"
  printf '  codex: %s — %s\n' "$codex_status" "$codex_detail"
  printf '  plugin manifest: %s — %s\n' "$manifest_status" "$manifest_detail"
  printf '  native hooks: %s\n' "$hooks_status"
  printf '  ALIVE product conflicts: %s — %s\n' "$conflicts_status" "$conflicts_detail"
  printf '  shared runtime: %s — %s\n' "$runtime_status" "$runtime_detail"
  printf '  world orientation cache: %s — %s\n' "$orientation_status" "$orientation_detail"
  printf '  index injection boundary: %s — %s\n' "$injection_status" "$injection_detail"
  printf '  MCP environment: %s — %s\n' "$mcp_status" "$mcp_detail"
fi

[ "$overall" != "fail" ]
