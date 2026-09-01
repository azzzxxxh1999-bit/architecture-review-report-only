#!/usr/bin/env python3
"""Source snapshot and project classification helpers for version lifecycle."""

import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

SCHEMA_VERSION = 1
SOURCE_EXCLUDES = (
    "/.codemap/", "/.git/", "/.svn/", "/.hg/", "/.idea/", "/.vs/",
    "/.codegraph/", "/.codex-tmp/", "/.codex-local-history/",
    "/node_modules/", "/vendor/", "/third_party/", "/external/",
    "/.venv/", "/venv/", "/__pycache__/", "/.pytest_cache/",
    "/dist/", "/build/", "/out/", "/output/", "/target/", "/bin/",
    "/obj/", "/coverage/", "/.next/", "/.nuxt/", "/.godot/",
    "/library/", "/temp/", "/logs/", "/qa_screenshots/",
)
SOURCE_FILE_EXCLUDES = (
    ".pyc", ".pyo", ".tmp", ".temp", ".log", ".cache", ".swp", ".swo",
    ".ds_store", "thumbs.db",
)
SENSITIVE_NAMES = {
    ".env", ".env.local", ".env.production", ".env.development",
    "credentials.json", "service-account.json", "id_rsa", "id_ed25519",
}
SENSITIVE_SUFFIXES = {".pem", ".p12", ".pfx", ".key"}

def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def now_iso():
    return _now_iso()


def read_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def architecture_state_view(state):
    """Drop volatile scan/render metadata before deciding whether an audit changed."""
    meta = dict(state.get("meta") or {})
    for key in ("generatedAt", "rev", "tracked_loc", "tracked_files", "locLine"):
        meta.pop(key, None)
    return {
        "meta": meta,
        "excludes": state.get("excludes", []),
        "bands": state.get("bands", []),
        "spine": state.get("spine", []),
        "reportThemes": state.get("reportThemes", []),
        "architectureLenses": state.get("architectureLenses", []),
        "architectureDimensions": state.get("architectureDimensions", []),
        "modules": state.get("modules", []),
    }

def normalize_rel(path):
    value = str(path).replace("\\", "/")
    while value.startswith("./"):
        value = value[2:]
    return value.lstrip("/")

def is_sensitive(name):
    low = name.lower()
    return low in SENSITIVE_NAMES or any(low.endswith(s) for s in SENSITIVE_SUFFIXES)

def path_excluded(rel, is_dir=False, exact_excludes=None):
    rel = normalize_rel(rel)
    low = "/" + rel.lower().strip("/") + ("/" if is_dir else "")
    if any(token in low for token in SOURCE_EXCLUDES):
        return True
    if not is_dir and any(low.endswith(token) for token in SOURCE_FILE_EXCLUDES):
        return True
    return rel in (exact_excludes or set())

def snapshot_fingerprint(entries):
    rows = ["{}:{}:{}".format(e["path"], e["size"], e["sha256"]) for e in entries]
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()

def collect_source_snapshot(root, previous=None, exact_excludes=None):
    root = os.path.realpath(root)
    previous_by_path = {e["path"]: e for e in (previous or {}).get("files", [])}
    exact_excludes = {normalize_rel(p) for p in (exact_excludes or set())}
    entries = []
    sensitive_skipped = []
    unreadable = []

    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        kept = []
        for d in dirs:
            full = os.path.join(current, d)
            rel = normalize_rel(os.path.relpath(full, root))
            if os.path.islink(full) or path_excluded(rel, True, exact_excludes):
                continue
            kept.append(d)
        dirs[:] = kept

        for name in files:
            full = os.path.join(current, name)
            rel = normalize_rel(os.path.relpath(full, root))
            if os.path.islink(full) or path_excluded(rel, False, exact_excludes):
                continue
            if is_sensitive(name):
                sensitive_skipped.append(rel)
                continue
            try:
                st = os.stat(full)
                old = previous_by_path.get(rel)
                if old and old.get("size") == st.st_size and old.get("mtimeNs") == st.st_mtime_ns:
                    digest = old["sha256"]
                else:
                    digest = sha256_file(full)
                entries.append({
                    "path": rel,
                    "size": st.st_size,
                    "mtimeNs": st.st_mtime_ns,
                    "sha256": digest,
                })
            except OSError as exc:
                unreadable.append({"path": rel, "error": str(exc)})

    entries.sort(key=lambda e: e["path"])
    return {
        "schemaVersion": SCHEMA_VERSION,
        "createdAt": now_iso(),
        "fileCount": len(entries),
        "totalBytes": sum(e["size"] for e in entries),
        "sourceFingerprint": snapshot_fingerprint(entries),
        "sensitiveSkipped": sorted(sensitive_skipped),
        "unreadable": unreadable,
        "files": entries,
    }

def snapshot_delta(previous, current):
    old = {e["path"]: e for e in (previous or {}).get("files", [])}
    new = {e["path"]: e for e in current.get("files", [])}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    modified = sorted(p for p in set(old) & set(new) if old[p]["sha256"] != new[p]["sha256"])
    return {
        "added": added,
        "removed": removed,
        "modified": modified,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "unchanged": len(set(old) & set(new)) - len(modified),
        },
    }

def detect_project_type(root):
    root_path = Path(root)
    game = (root_path / "project.godot").is_file()
    game = game or (root_path / "game" / "project.godot").is_file()
    game = game or bool(list(root_path.glob("*.uproject")))
    game = game or ((root_path / "Assets").is_dir() and (root_path / "ProjectSettings").is_dir())
    web = (root_path / ".openai" / "hosting.json").is_file()
    web = web or (root_path / "index.html").is_file()
    web = web or any((root_path / n).is_file() for n in (
        "next.config.js", "next.config.mjs", "vite.config.js", "vite.config.ts",
        "astro.config.mjs", "svelte.config.js", "nuxt.config.ts",
    ))

    package = root_path / "package.json"
    if package.is_file():
        try:
            data = read_json(package)
            deps = set((data.get("dependencies") or {})) | set((data.get("devDependencies") or {}))
            web = web or bool(deps & {
                "next", "react", "react-dom", "vue", "svelte", "astro", "vite",
                "@angular/core", "nuxt", "solid-js",
            })
            game = game or bool(deps & {
                "three", "phaser", "pixi.js", "@pixi/core", "babylonjs", "@babylonjs/core",
            })
        except (OSError, ValueError, TypeError) as exc:
            # Keep filesystem heuristics usable, but make malformed metadata
            # visible so a later "unknown project" failure is diagnosable.
            print("version: warning - cannot read package.json: {}".format(exc),
                  file=sys.stderr)

    return "hybrid" if web and game else "website" if web else "game" if game else "unknown"
