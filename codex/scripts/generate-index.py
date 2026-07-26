#!/usr/bin/env python3
"""ALIVE World Index Generator v2

Walks the tree, reads all key.md + context.manifest.yaml frontmatter, dumps to _index.yaml + _index.json.
Runs: post-save hook, on-demand via alive:map, or manually.

v2 fixes:
- Correctly identifies walnut names when key.md is inside _core/
- Deduplicates walnut entries (prefers _core/ version)
- Skips template walnuts ({{placeholders}})
- Extracts links (wikilinks), tags, and people names
- Outputs JSON alongside YAML for graph consumption

Usage: python3 .alive/scripts/generate-index.py [world-root]
"""

import argparse
import json
import os
import re
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path


def extract_frontmatter(filepath):
    """Extract YAML frontmatter from a markdown file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, UnicodeDecodeError):
        return {}

    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if match:
        frontmatter = match.group(1)
    elif str(filepath).endswith((".yaml", ".yml")):
        frontmatter = content
    else:
        return {}

    fm = {}
    lines = frontmatter.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        kv = re.match(r'^(\w[\w-]*)\s*:\s*(.*)', line)
        if kv:
            key = kv.group(1)
            val = kv.group(2).strip()

            # Check for multi-line list (next lines start with "  - ")
            if val == '' or val == '[]':
                items = []
                j = i + 1
                while j < len(lines) and re.match(r'^\s+-\s', lines[j]):
                    item_match = re.match(r'^\s+-\s+(.*)', lines[j])
                    if item_match:
                        items.append(item_match.group(1).strip())
                    j += 1
                if items:
                    fm[key] = items
                    i = j
                    continue
                else:
                    fm[key] = val
            else:
                # Remove quotes
                if (val.startswith('"') and val.endswith('"')) or \
                   (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                fm[key] = val
        i += 1
    return fm


def strip_wikilinks(val):
    """Strip [[brackets]] from a value, returning the inner name."""
    if isinstance(val, str):
        return re.sub(r'\[\[([^\]]*)\]\]', r'\1', val).strip()
    return val


def parse_inline_list(val):
    """Parse [a, b, c] or [[a]], [[b]] into a clean list.
    Handles wikilink syntax gracefully — [[name]] becomes name."""
    if not val:
        return []
    val = val.strip()
    if val.startswith('[') and val.endswith(']'):
        val = val[1:-1]
    items = []
    for x in val.split(','):
        x = x.strip().strip('"').strip("'")
        x = strip_wikilinks(x)
        if x:
            items.append(x)
    return items


def extract_yaml_list(content, field):
    """Extract an indented YAML list field without parsing unrelated YAML."""
    lines = content.splitlines()
    marker = re.compile(r"^" + re.escape(field) + r":[ \t]*(?:\[\])?[ \t]*$")
    item = re.compile(r"^[ \t]+-[ \t]+(.*)$")
    for index, line in enumerate(lines):
        if not marker.match(line):
            continue
        values = []
        for following in lines[index + 1:]:
            matched = item.match(following)
            if matched:
                value = matched.group(1).strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                values.append(value)
                continue
            if following.startswith((" ", "\t")) or not following.strip():
                continue
            break
        return values
    return []


def atomic_write_text(path, text):
    """Atomically replace a text file without exposing partial output."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temporary_name, destination)
    finally:
        Path(temporary_name).unlink(missing_ok=True)


def _stage_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.candidate-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        return temporary
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _restore_bytes(path: Path, previous: bytes | None) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.rollback-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(previous)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _validate_index_candidate(text: str) -> dict:
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("index candidate root must be an object")
    generation = payload.get("generation")
    if not isinstance(generation, str) or not re.fullmatch(r"[a-f0-9]{32}", generation):
        raise ValueError("index candidate generation marker is invalid")
    if not isinstance(payload.get("generated"), str):
        raise ValueError("index candidate generated timestamp is invalid")
    if not isinstance(payload.get("stats"), dict):
        raise ValueError("index candidate stats must be an object")
    for field in ("walnuts", "people", "recent_sessions"):
        if not isinstance(payload.get(field), list):
            raise ValueError(f"index candidate {field} must be a list")
    return payload


def replace_index_pair(yaml_path: Path, yaml_text: str, json_path: Path, json_text: str) -> None:
    """Replace the JSON-compatible YAML/JSON pair or restore the prior pair."""
    yaml_candidate = _validate_index_candidate(yaml_text)
    json_candidate = _validate_index_candidate(json_text)
    if yaml_candidate != json_candidate:
        raise ValueError("index candidate pair does not contain identical data")

    yaml_previous = yaml_path.read_bytes() if yaml_path.is_file() else None
    json_previous = json_path.read_bytes() if json_path.is_file() else None
    yaml_temporary = _stage_text(yaml_path, yaml_text)
    json_temporary = _stage_text(json_path, json_text)
    replaced_yaml = False
    replaced_json = False
    try:
        os.replace(yaml_temporary, yaml_path)
        replaced_yaml = True
        if os.environ.get("ALIVE_INDEX_TEST_FAIL_SECOND_REPLACE"):
            raise RuntimeError("ALIVE_INDEX_TEST_FAIL_SECOND_REPLACE requested")
        os.replace(json_temporary, json_path)
        replaced_json = True
        installed_yaml = _validate_index_candidate(yaml_path.read_text(encoding="utf-8"))
        installed_json = _validate_index_candidate(json_path.read_text(encoding="utf-8"))
        if installed_yaml != installed_json:
            raise RuntimeError("installed index pair generation mismatch")
    except BaseException:
        rollback_errors: list[str] = []
        for path, previous, replaced in (
            (yaml_path, yaml_previous, replaced_yaml),
            (json_path, json_previous, replaced_json),
        ):
            if not replaced:
                continue
            try:
                _restore_bytes(path, previous)
            except OSError as error:
                rollback_errors.append(f"{path.name}: {error}")
        if rollback_errors:
            marker = yaml_path.parent / "_index.mismatch"
            atomic_write_text(
                marker,
                "Index pair rollback failed; regenerate before using either index.\n"
                + "\n".join(rollback_errors)
                + "\n",
            )
            raise RuntimeError("index pair rollback failed: " + "; ".join(rollback_errors))
        raise
    finally:
        yaml_temporary.unlink(missing_ok=True)
        json_temporary.unlink(missing_ok=True)


def build_codex_orientation(world_root: Path, index_payload: dict, index_path: Path) -> None:
    """Lazy Codex-only opt-in; the shared/legacy generator stays standalone."""
    try:
        from orientation import build_and_write
    except ImportError as error:
        raise RuntimeError(
            "--build-orientation requires the packaged Codex orientation.py"
        ) from error
    build_and_write(world_root, index_payload, index_path=index_path)


def extract_wikilinks(val):
    """Extract [[name]] references from a string or list.
    Also handles bare names and mixed formats."""
    if isinstance(val, list):
        result = []
        for item in val:
            s = str(item).strip().strip('"').strip("'")
            # Try extracting wikilink
            found = re.findall(r'\[\[([^\]]+)\]\]', s)
            if found:
                result.extend(found)
            elif s and not s.startswith('['):
                # Bare name without brackets
                result.append(s)
        return result
    s = str(val)
    found = re.findall(r'\[\[([^\]]+)\]\]', s)
    return found if found else []


def parse_people_names(filepath):
    """Extract people names from multi-line people: block in frontmatter."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (IOError, UnicodeDecodeError):
        return []

    match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not match:
        return []

    names = []
    in_people = False
    for line in match.group(1).split('\n'):
        if re.match(r'^people\s*:', line):
            in_people = True
            continue
        if in_people:
            if re.match(r'^\w', line):  # New top-level key
                break
            name_match = re.match(r'^\s+-?\s*name\s*:\s*(.+)', line)
            if name_match:
                name = name_match.group(1).strip().strip('"').strip("'")
                names.append(name)
    return names


def detect_domain(rel_path):
    """Determine ALIVE domain from relative path."""
    parts = rel_path.split(os.sep)
    if not parts:
        return "unknown"
    first = parts[0]
    domain_map = {
        "01_Archive": "archive",
        "02_Life": "life",
        "03_Inbox": "inputs",
        "04_Ventures": "ventures",
        "05_Experiments": "experiments",
    }
    domain = domain_map.get(first, "unknown")
    if domain == "life" and len(parts) > 1 and parts[1] == "people":
        return "people"
    return domain


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("world_root", nargs="?", default=os.getcwd())
    parser.add_argument(
        "--build-orientation",
        action="store_true",
        help="Codex-only opt-in: build the bounded orientation after committing the index",
    )
    args = parser.parse_args()
    world_root = args.world_root
    world_root = os.path.abspath(world_root)
    alive_dir = os.path.join(world_root, '.alive')
    index_file = os.path.join(alive_dir, '_index.yaml')
    json_file = os.path.join(alive_dir, '_index.json')
    timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Dict to dedup — keyed by walnut rel_path
    walnut_entries = {}
    people_entries = {}
    total_capsules = 0

    for root, dirs, files in os.walk(world_root):
        # Skip hidden dirs, node_modules, etc.
        dirs[:] = [d for d in dirs if not d.startswith('.')
                   and d not in ('node_modules', 'Icon\r', '__pycache__',
                                 'dist', 'build', '.next', 'target')]

        if 'key.md' not in files:
            continue

        keyfile = os.path.join(root, 'key.md')

        # Determine walnut directory — if key.md is inside _core/ or _kernel/, walnut is parent
        walnut_dir = root
        dir_name = os.path.basename(root)
        in_core = dir_name in ('_core', '_kernel')
        if in_core:
            walnut_dir = os.path.dirname(root)

        walnut_name = os.path.basename(walnut_dir)
        rel_path = os.path.relpath(walnut_dir, world_root)

        # Skip world root
        if rel_path == '.':
            continue

        # Dedup: if already seen and this ISN'T the _core version, skip
        # (_core version overwrites flat version since os.walk visits subdirs after parent)
        if rel_path in walnut_entries and not in_core:
            continue
        if rel_path in people_entries and not in_core:
            continue

        fm = extract_frontmatter(keyfile)

        # Skip template walnuts
        if any('{{' in str(v) for v in fm.values()):
            continue

        domain = detect_domain(rel_path)
        wtype = fm.get('type', 'unknown')
        goal = fm.get('goal', '')
        rhythm = fm.get('rhythm', '')
        created = fm.get('created', '')

        # Extract parent
        parent_raw = fm.get('parent', '')
        parent_links = extract_wikilinks(parent_raw)
        parent = parent_links[0] if parent_links else ''

        # Extract links (wikilinks)
        links_raw = fm.get('links', '')
        if isinstance(links_raw, list):
            links = extract_wikilinks(links_raw)
        else:
            links = extract_wikilinks(links_raw)

        # Extract tags
        tags_raw = fm.get('tags', '')
        if isinstance(tags_raw, list):
            tags = tags_raw
        else:
            tags = parse_inline_list(tags_raw)

        # Extract people names
        people_names = parse_people_names(keyfile)

        # Read now.json — v3 first (_kernel/now.json), then v2 fallbacks
        phase = ''
        updated = ''
        next_action = ''
        active_capsule = ''
        task_counts = {}
        bundle_summary = {}
        blockers = []
        recent_sessions = []
        children_raw = {}
        for candidate in [os.path.join(walnut_dir, '_kernel', 'now.json'),
                          os.path.join(walnut_dir, '_kernel', '_generated', 'now.json'),
                          os.path.join(walnut_dir, '_core', '_kernel', '_generated', 'now.json')]:
            if os.path.isfile(candidate):
                try:
                    with open(candidate, 'r', encoding='utf-8') as nf:
                        now_data = json.load(nf)
                    phase = now_data.get('phase', '')
                    updated = now_data.get('updated', '')
                    next_raw = now_data.get('next', '')
                    if isinstance(next_raw, dict):
                        next_action = next_raw.get('action', '')
                    else:
                        next_action = str(next_raw) if next_raw else ''
                    active_capsule = now_data.get('bundle', '')

                    # Enrich: task counts
                    tasks_raw = now_data.get('unscoped_tasks', {})
                    task_counts = tasks_raw.get('counts', {})

                    # Enrich: bundle summary
                    bundles_raw = now_data.get('bundles', {})
                    bundle_summary = bundles_raw.get('summary', {})

                    # Enrich: blockers
                    blockers = now_data.get('blockers', [])

                    # Enrich: recent sessions
                    recent_sessions = now_data.get('recent_sessions', [])

                    # Enrich: children
                    children_raw = now_data.get('children', {})

                except (json.JSONDecodeError, IOError):
                    task_counts = {}
                    bundle_summary = {}
                    blockers = []
                    recent_sessions = []
                    children_raw = {}
                break

        # Count bundles (v3: folders with context.manifest.yaml in walnut root)
        # Also check legacy _capsules/ and _core/_capsules/
        capsule_entries = []
        capsule_count = 0
        seen_bundles = set()

        # v3: scan walnut root for bundle folders
        if os.path.isdir(walnut_dir):
            for item in sorted(os.listdir(walnut_dir)):
                if item.startswith(('.', '_')):
                    continue
                item_path = os.path.join(walnut_dir, item)
                if not os.path.isdir(item_path):
                    continue
                manifest = os.path.join(item_path, 'context.manifest.yaml')
                if os.path.isfile(manifest):
                    capsule_count += 1
                    seen_bundles.add(item)
                    cfm = extract_frontmatter(manifest)
                    capsule_entries.append({
                        'name': item,
                        'goal': cfm.get('goal', cfm.get('outcome', '')),
                        'status': cfm.get('status', cfm.get('phase', 'draft')),
                        'updated': cfm.get('updated', ''),
                    })

        # v2 fallback: check _capsules/ and _core/_capsules/
        for cap_dir in [os.path.join(walnut_dir, '_core', '_capsules'),
                        os.path.join(walnut_dir, '_capsules')]:
            if os.path.isdir(cap_dir):
                for item in sorted(os.listdir(cap_dir)):
                    if item in seen_bundles:
                        continue
                    cap_path = os.path.join(cap_dir, item)
                    if os.path.isdir(cap_path):
                        capsule_count += 1
                        comp = os.path.join(cap_path, 'context.manifest.yaml')
                        if os.path.isfile(comp):
                            cfm = extract_frontmatter(comp)
                            capsule_entries.append({
                                'name': item,
                                'goal': cfm.get('goal', ''),
                                'status': cfm.get('status', cfm.get('phase', 'draft')),
                                'updated': cfm.get('updated', ''),
                            })
                break

        # Count squirrel sessions
        squirrel_count = 0
        for sq_dir in [os.path.join(walnut_dir, '_core', '_squirrels'),
                       os.path.join(walnut_dir, '_squirrels')]:
            if os.path.isdir(sq_dir):
                squirrel_count = len([f for f in os.listdir(sq_dir)
                                      if f.endswith('.yaml')])
                break

        is_archived = rel_path.startswith('01_Archive')
        total_capsules += capsule_count

        # Session count from recent_sessions
        session_count = len(recent_sessions)
        last_session = recent_sessions[0].get('date', '') if recent_sessions else ''

        entry = {
            'name': walnut_name,
            'path': rel_path,
            'type': wtype,
            'goal': goal,
            'phase': phase,
            'rhythm': rhythm,
            'updated': updated,
            'created': created,
            'domain': domain,
            'archived': is_archived,
            'capsule_count': capsule_count,
            'squirrel_sessions': squirrel_count,
            'active_capsule': active_capsule,
            'next': next_action,
            'capsules': capsule_entries,
            'links': links,
            'tags': tags,
            'people': people_names,
            'parent': parent,
            # Enriched from now.json
            'task_counts': task_counts,
            'bundle_summary': bundle_summary,
            'blockers': blockers,
            'session_count': session_count,
            'last_session': last_session,
            'children': list(children_raw.keys()) if isinstance(children_raw, dict) else [],
        }

        target = people_entries if (wtype == 'person' or domain == 'people') else walnut_entries
        target[rel_path] = entry

    # ─── Infer parent-child from filesystem hierarchy ───
    # For every walnut, find the nearest ancestor walnut by path
    all_entries = {**walnut_entries, **people_entries}
    all_paths = sorted(all_entries.keys())

    for rel_path, entry in all_entries.items():
        if entry.get('parent'):
            continue  # Already has explicit parent from key.md
        # Walk up the path to find nearest ancestor walnut
        parts = rel_path.split(os.sep)
        for depth in range(len(parts) - 1, 0, -1):
            candidate = os.sep.join(parts[:depth])
            if candidate in all_entries and candidate != rel_path:
                entry['parent'] = all_entries[candidate]['name']
                break

    # ─── Bidirectional people-walnut links ───
    # People walnuts often have links: back to ventures/experiments.
    # Inject those as people references in the target walnuts.
    walnut_by_name = {e['name']: e for e in walnut_entries.values()}
    people_by_name = {e['name']: e for e in people_entries.values()}

    for pname, pentry in people_entries.items():
        person_name = pentry['name']
        person_links = pentry.get('links', [])
        for target in person_links:
            if target in walnut_by_name:
                # Add this person to the walnut's people list if not already there
                existing = walnut_by_name[target].get('people', [])
                if person_name not in existing:
                    existing.append(person_name)
                    walnut_by_name[target]['people'] = existing

    # Also: for each walnut's people, if that person has a people walnut with
    # links, propagate those links as cross-references
    for wname, wentry in walnut_by_name.items():
        for person_name in wentry.get('people', []):
            # Find matching people walnut by name
            for pname, pentry in people_entries.items():
                if pentry['name'] == person_name:
                    for target in pentry.get('links', []):
                        if target in walnut_by_name and target != wname:
                            # This person connects these two walnuts
                            pass  # The graph script handles this via people bridge nodes

    # Convert to sorted lists
    walnuts = list(walnut_entries.values())
    people = list(people_entries.values())

    # World-level squirrels
    world_sq_dir = os.path.join(world_root, '.alive', '_squirrels')
    world_sq_count = 0
    if os.path.isdir(world_sq_dir):
        world_sq_count = len([f for f in os.listdir(world_sq_dir)
                              if f.endswith('.yaml')])

    # ─── Recent sessions + unsigned stash count ───
    recent_sessions = []
    unsigned_with_stash = 0
    if os.path.isdir(world_sq_dir):
        sq_files = [f for f in os.listdir(world_sq_dir) if f.endswith('.yaml')]
        sq_files.sort(
            key=lambda f: os.path.getmtime(os.path.join(world_sq_dir, f)),
            reverse=True
        )

        def extract_sq_field(content, field):
            """Extract a field value from squirrel YAML via regex."""
            m = re.search(r'^' + re.escape(field) + r'[ \t]*:[ \t]*(.*)', content, re.MULTILINE)
            if not m:
                return ''
            val = m.group(1).strip()
            if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or
                                   (val[0] == "'" and val[-1] == "'")):
                val = val[1:-1]
            return val

        for sq_file in sq_files:
            sq_path = os.path.join(world_sq_dir, sq_file)
            try:
                with open(sq_path, 'r', encoding='utf-8') as sf:
                    sq_content = sf.read()
            except (IOError, UnicodeDecodeError):
                continue

            saves_str = extract_sq_field(sq_content, 'saves')
            saves_val = 0
            try:
                saves_val = int(saves_str)
            except (ValueError, TypeError):
                pass

            has_empty_stash = bool(re.search(r'^stash\s*:\s*\[\s*\]\s*$', sq_content, re.MULTILINE))
            has_stash_key = bool(re.search(r'^stash\s*:', sq_content, re.MULTILINE))
            if saves_val == 0 and has_stash_key and not has_empty_stash:
                stash_m = re.search(r'^stash\s*:.*\n(\s+-\s)', sq_content, re.MULTILINE)
                if stash_m:
                    unsigned_with_stash += 1

            if len(recent_sessions) < 10:
                session_id = extract_sq_field(sq_content, 'session_id')
                walnut_name = extract_sq_field(sq_content, 'walnut')
                started = extract_sq_field(sq_content, 'started')
                recovery = extract_sq_field(sq_content, 'recovery_state')
                bundle = extract_sq_field(sq_content, 'bundle')
                tags_list = extract_yaml_list(sq_content, 'tags')
                if not tags_list:
                    tags_list = parse_inline_list(extract_sq_field(sq_content, 'tags'))

                date = ''
                if started:
                    date_m = re.match(r'(\d{4}-\d{2}-\d{2})', started)
                    if date_m:
                        date = date_m.group(1)

                entry = {
                    'squirrel': session_id[:8] if session_id else sq_file[:8],
                    'walnut': walnut_name if walnut_name and walnut_name != 'null' else '',
                    'date': date,
                    'saves': saves_val,
                    'summary': recovery,
                }
                if bundle:
                    entry['bundle'] = bundle
                if tags_list:
                    entry['tags'] = tags_list

                recent_sessions.append(entry)

    # Inputs count
    inputs_dir = os.path.join(world_root, '03_Inbox')
    input_count = 0
    if os.path.isdir(inputs_dir):
        input_count = len([f for f in os.listdir(inputs_dir)
                           if not f.startswith('.') and f != 'Icon\r'])

    # Sort by domain then name
    domain_order = {'life': 0, 'ventures': 1, 'experiments': 2, 'archive': 3,
                    'unknown': 4}
    walnuts.sort(key=lambda w: (domain_order.get(w['domain'], 4), w['name']))
    people.sort(key=lambda p: p['name'])

    # Build one typed structure. JSON is a valid YAML 1.2 subset, so writing
    # the same pretty JSON to both paths avoids YAML scalar coercion and
    # guarantees every dynamic key/value is quoted and Unicode-safe.
    def clean(entry):
        return {k: v for k, v in entry.items()
                if v and v != [] and v != 0 and v != False}

    def clean_session(entry):
        """Clean session entry but preserve saves: 0 since it's meaningful."""
        return {k: v for k, v in entry.items()
                if k == 'saves' or (v and v != [] and v is not False)}

    json_data = {
        'generated': timestamp,
        'generation': uuid.uuid4().hex,
        'stats': {
            'walnuts': len(walnuts),
            'people': len(people),
            'capsules': total_capsules,
            'sessions': world_sq_count,
            'inputs': input_count,
            'unsigned_with_stash': unsigned_with_stash,
        },
        'walnuts': [clean(w) for w in walnuts],
        'people': [clean(p) for p in people],
        'recent_sessions': [clean_session(rs) for rs in recent_sessions],
    }
    json_output = json.dumps(
        json_data, indent=2, ensure_ascii=False, sort_keys=True, default=str
    ) + "\n"
    yaml_output = json_output

    if os.environ.get('ALIVE_INDEX_TEST_FAIL'):
        raise RuntimeError('ALIVE_INDEX_TEST_FAIL requested')

    replace_index_pair(
        Path(index_file), yaml_output, Path(json_file), json_output
    )
    if args.build_orientation:
        build_codex_orientation(Path(world_root), json_data, Path(json_file))

    print(f"Index: {index_file}")
    print(f"JSON:  {json_file}")
    print(f"Walnuts: {len(walnuts)} | People: {len(people)} | "
          f"Capsules: {total_capsules} | Inputs: {input_count} | "
          f"Sessions: {world_sq_count}")


if __name__ == '__main__':
    main()
