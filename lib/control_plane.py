"""Client-side control plane: reconcile a client against CONTROL/manifest.json
on session start. Stdlib only. See
docs/superpowers/specs/2026-07-05-control-plane-design.md."""
import json
import os
import shutil
from pathlib import Path


def version_tuple(s):
    """Parse a dotted version like '0.0.1' into a comparable tuple of ints."""
    return tuple(int(x) for x in str(s).split("."))


DEFAULT_APPLIED = {"skills_version": 0, "structure_version": 0,
                   "policy_version": 0, "announced_mcps": []}


def read_manifest(repo):
    return json.loads((Path(repo) / "CONTROL" / "manifest.json").read_text())


def read_applied(repo):
    p = Path(repo) / ".applied.json"
    if not p.exists():
        return dict(DEFAULT_APPLIED)
    return json.loads(p.read_text())


def _atomic_write(path, text):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def write_applied(repo, applied):
    _atomic_write(Path(repo) / ".applied.json",
                  json.dumps(applied, indent=2, sort_keys=True) + "\n")


_OFFLIMITS_TOP = {"private", ".claude", ".git"}


def _safe_path(repo, relpath):
    """Resolve a repo-relative path and enforce containment; raise ValueError
    on escape or an off-limits top-level area."""
    if os.path.isabs(relpath) or ".." in Path(relpath).parts:
        raise ValueError(f"unsafe path: {relpath}")
    repo = Path(repo).resolve()
    resolved = (repo / relpath).resolve()
    if resolved != repo and repo not in resolved.parents:
        raise ValueError(f"path escapes repo: {relpath}")
    rel = resolved.relative_to(repo)
    if rel.parts and rel.parts[0] in _OFFLIMITS_TOP:
        raise ValueError(f"off-limits path: {relpath}")
    return repo / relpath


def apply_migration(repo, migration):
    """Apply declarative ops idempotently; return the set of repo-relative
    paths touched (empty when the tree is already in the target state)."""
    repo = Path(repo)
    touched = set()
    for op in migration.get("ops", []):
        kind = op["op"]
        if kind == "make_dir":
            p = _safe_path(repo, op["path"])
            if not p.exists():
                p.mkdir(parents=True, exist_ok=True)
                touched.add(op["path"])
        elif kind == "keep_file":
            p = _safe_path(repo, op["path"])
            if not p.exists():
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("")
                touched.add(op["path"])
        elif kind == "delete":
            p = _safe_path(repo, op["path"])
            if p.is_dir():
                shutil.rmtree(p); touched.add(op["path"])
            elif p.exists():
                p.unlink(); touched.add(op["path"])
        elif kind in ("move", "rename"):
            src = _safe_path(repo, op["from"]); dst = _safe_path(repo, op["to"])
            s_exists, d_exists = src.exists(), dst.exists()
            if s_exists and d_exists:
                raise ValueError(f"move collision: {op['from']} -> {op['to']}")
            if s_exists and not d_exists:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                touched.add(op["from"]); touched.add(op["to"])
        else:
            raise ValueError(f"unknown op: {kind}")
    return touched


def _migration_id(path):
    """Leading integer of an 'NNNN-slug.json' filename, or None if not numeric."""
    head = Path(path).name.split("-", 1)[0]
    return int(head) if head.isdigit() else None


def pending_migrations(repo, applied):
    md = Path(repo) / "CONTROL" / "migrations"
    if not md.is_dir():
        return []
    out = []
    for p in sorted(md.glob("*.json")):
        mid = _migration_id(p)
        if mid is None:
            continue
        if mid > applied.get("structure_version", 0):
            out.append({"id": mid, "path": p, "data": json.loads(p.read_text())})
    return sorted(out, key=lambda m: m["id"])


def evaluate_gate(manifest, client_version, pending_migration_data):
    """Return a list of gate reasons (empty = clear)."""
    reasons = []
    cv = version_tuple(client_version)
    minv = manifest.get("min_client_version") or "0.0.0"
    if cv < version_tuple(minv):
        reasons.append(f"client {client_version} is older than required {minv}")
    for m in pending_migration_data:
        mmin = m.get("min_client_version")
        if mmin and cv < version_tuple(mmin):
            reasons.append(f"a pending migration requires client >= {mmin}")
    return reasons
