#!/usr/bin/env python3
"""Pure module/dependency delta helpers for version lifecycle."""

import fnmatch
import hashlib
from pathlib import PurePosixPath


def stable_json_hash(value):
    import json
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def normalize_rel(path):
    value = str(path).replace("\\\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")

def module_map(state):
    return {m.get("id"): m for m in state.get("modules", []) if m.get("id")}

def module_delta(previous_state, current_state):
    old = module_map(previous_state or {})
    new = module_map(current_state)
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    content_changed = sorted(
        mid for mid in set(old) & set(new)
        if old[mid].get("contentHash") != new[mid].get("contentHash")
    )
    audit_changed = sorted(
        mid for mid in set(old) & set(new)
        if any(old[mid].get(k) != new[mid].get(k)
               for k in ("score", "grade", "tags", "findings", "auditedHash"))
    )
    return {
        "added": added,
        "removed": removed,
        "contentChanged": content_changed,
        "auditChanged": audit_changed,
    }

def keyed_state_delta(previous_state, current_state, key):
    old = {str(item.get("id")): item for item in (previous_state or {}).get(key, []) if item.get("id")}
    new = {str(item.get("id")): item for item in (current_state or {}).get(key, []) if item.get("id")}
    return {
        "added": sorted(set(new) - set(old)),
        "removed": sorted(set(old) - set(new)),
        "changed": sorted(
            item_id for item_id in set(old) & set(new)
            if stable_json_hash(old[item_id]) != stable_json_hash(new[item_id])
        ),
    }

def architecture_delta(previous_state, current_state):
    return {
        "dimensions": keyed_state_delta(previous_state, current_state, "architectureDimensions"),
        "lenses": keyed_state_delta(previous_state, current_state, "architectureLenses"),
    }

def architecture_delta_count(delta):
    return sum(len(values) for group in delta.values() for values in group.values())

def reverse_dependency_scope(state, changed_ids):
    """Return direct and transitive consumers for incremental-audit scoping."""
    modules = module_map(state)
    changed = sorted(mid for mid in set(changed_ids) if mid in modules)
    reverse = {mid: set() for mid in modules}
    for mid, mod in modules.items():
        for dep in mod.get("deps") or []:
            if dep in reverse:
                reverse[dep].add(mid)
    direct = sorted({consumer for mid in changed for consumer in reverse.get(mid, set())}
                    - set(changed))
    seen = set(changed)
    queue = list(changed)
    while queue:
        current = queue.pop(0)
        for consumer in sorted(reverse.get(current, set())):
            if consumer not in seen:
                seen.add(consumer)
                queue.append(consumer)
    transitive = sorted(seen - set(changed) - set(direct))
    return {
        "changedModules": changed,
        "directConsumers": direct,
        "transitiveConsumers": transitive,
        "suggestedAuditScope": changed + direct,
    }

def issue_records(state):
    """Stable issue identities for human-facing incremental summaries."""
    records = {}
    for mod in state.get("modules") or []:
        mid = mod.get("id")
        for finding in mod.get("findings") or []:
            record = {
                "kind": "module-finding",
                "moduleId": mid,
                "severity": finding.get("sev"),
                "location": finding.get("loc"),
                "text": finding.get("text"),
            }
            key = stable_json_hash(record)
            records[key] = record
    for dim in state.get("architectureDimensions") or []:
        if dim.get("status") not in {"warning", "risk"}:
            continue
        record = {
            "kind": "architecture-dimension",
            "dimensionId": dim.get("id"),
            "status": dim.get("status"),
            "summary": dim.get("summary"),
        }
        key = "dimension:" + str(dim.get("id"))
        records[key] = record
    return records

def issue_delta(previous_state, current_state):
    previous = issue_records(previous_state or {})
    current = issue_records(current_state)
    old_keys, new_keys = set(previous), set(current)
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    persisting = sorted(old_keys & new_keys)
    old_unknown = {d.get("id") for d in (previous_state or {}).get("architectureDimensions", [])
                   if d.get("status") == "unknown"}
    new_unknown = {d.get("id") for d in current_state.get("architectureDimensions", [])
                   if d.get("status") == "unknown"}
    return {
        "newIssues": len(added),
        "resolvedIssues": len(removed),
        "persistingIssues": len(persisting),
        "unknownChanged": len(old_unknown ^ new_unknown),
        "new": [current[key] for key in added],
        "resolved": [previous[key] for key in removed],
        "persisting": [current[key] for key in persisting],
        "unknownDimensions": sorted(new_unknown),
    }

def flatten_values(values):
    result = []
    for value in values or []:
        for item in str(value).split(","):
            item = item.strip()
            if item and item not in result:
                result.append(item)
    return result

def glob_matches(path, pattern):
    path = normalize_rel(path)
    pattern = normalize_rel(pattern)
    return (fnmatch.fnmatchcase(path, pattern)
            or PurePosixPath(path).match(pattern)
            or (pattern.startswith("**/") and fnmatch.fnmatchcase(path, pattern[3:])))

def map_changed_files_to_modules(changed_files, state):
    mapped = {}
    unmapped = []
    modules = state.get("modules", [])
    for path in changed_files:
        owners = []
        for mod in modules:
            patterns = mod.get("paths") or []
            if isinstance(patterns, str):
                patterns = [patterns]
            if any(glob_matches(path, pat) for pat in patterns):
                owners.append(mod.get("id"))
        if owners:
            mapped[path] = owners
        else:
            unmapped.append(path)
    return mapped, sorted(unmapped)

def score_summary(state):
    modules = state.get("modules", [])
    scored = [m for m in modules if m.get("score") is not None]
    grades = {g: 0 for g in ("A", "B", "C", "D", "F")}
    severities = {s: 0 for s in ("HIGH", "MED", "LOW")}
    for mod in scored:
        grade = mod.get("grade")
        if grade in grades:
            grades[grade] += 1
        for finding in mod.get("findings") or []:
            sev = finding.get("sev")
            if sev in severities:
                severities[sev] += 1
    average = round(sum(m["score"] for m in scored) / len(scored), 2) if scored else None
    return {
        "moduleCount": len(modules),
        "scoredModules": len(scored),
        "averageScore": average,
        "gradeCounts": grades,
        "findingCounts": severities,
    }

