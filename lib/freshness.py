"""Freshness / TTL: track last_verified on notes, warn on staleness, re-verify
via the /hive-audit skill. Stdlib only. See
docs/superpowers/specs/2026-07-05-freshness-design.md."""
import hashlib
import json
import os
import re
from datetime import date
from pathlib import Path

from lib.gitsync import run_git, push_paths

DEFAULT_SCAN_ROOTS = ["org", "product", "engineering", "design", "customers",
                      "market", "knowledge", "projects", "decisions", "private"]


def read_health_config(repo):
    p = Path(repo) / "CONTROL" / "health.json"
    if not p.exists():
        return {"default_horizon_days": 180, "horizons": {},
                "scan_roots": list(DEFAULT_SCAN_ROOTS)}
    cfg = json.loads(p.read_text())
    cfg.setdefault("default_horizon_days", 180)
    cfg.setdefault("horizons", {})
    cfg.setdefault("scan_roots", list(DEFAULT_SCAN_ROOTS))
    return cfg


def parse_frontmatter(path):
    """Minimal scalar front-matter reader (NOT full YAML). Returns a dict of
    scalar key/value pairs from a leading '--- ... ---' block, or None if the
    file has no such block."""
    text = Path(path).read_text()
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value and value[0] in "\"'":
            q = value[0]
            end = value.find(q, 1)
            value = value[1:end] if end != -1 else value[1:]
        else:
            m = re.search(r"\s+#", value)
            if m:
                value = value[:m.start()].strip()
        if key:
            fm[key] = value
    return fm


def _parse_date(s):
    try:
        return date.fromisoformat(str(s))
    except (ValueError, TypeError):
        return None


def note_status(frontmatter, today, config):
    lv = _parse_date(frontmatter.get("last_verified"))
    if lv is None:
        return None  # untracked
    rb = _parse_date(frontmatter.get("review_by"))
    if rb is not None and today > rb:
        return "expired"
    horizon = config.get("horizons", {}).get(
        frontmatter.get("type"), config.get("default_horizon_days", 180))
    if (today - lv).days > horizon:
        return "stale"
    return "fresh"


def scan(repo, config, today):
    repo = Path(repo)
    out = []
    for root in config.get("scan_roots", DEFAULT_SCAN_ROOTS):
        base = repo / root
        if not base.is_dir():
            continue  # missing root skipped silently
        for p in sorted(base.rglob("*.md")):
            if not p.is_file():
                continue
            fm = parse_frontmatter(p)
            if not fm:
                continue
            status = note_status(fm, today, config)
            if status is None:
                continue  # untracked
            lv = _parse_date(fm.get("last_verified"))
            out.append({
                "path": p.relative_to(repo).as_posix(),
                "type": fm.get("type"),
                "status": status,
                "last_verified": fm.get("last_verified"),
                "age_days": (today - lv).days,
            })
    return out


def _atomic_write(path, text):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def stamp(path, today):
    """Rewrite the note's existing `last_verified:` line to `today`. Raises
    ValueError if the note has no front-matter block or no last_verified line."""
    path = Path(path)
    lines = path.read_text().splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"no front-matter block: {path}")
    new_iso = today.isoformat()
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            break
        if lines[i].split(":", 1)[0].strip() == "last_verified":
            eol = "\n" if lines[i].endswith("\n") else ""
            lines[i] = f"last_verified: {new_iso}{eol}"
            _atomic_write(path, "".join(lines))
            return
    raise ValueError(f"no last_verified line in front-matter: {path}")


def _body_after_frontmatter(text):
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:])
    return text


def _normalized_hash(text):
    body = _body_after_frontmatter(text)
    norm = re.sub(r"\s+", " ", body).strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def find_duplicates(repo, config):
    repo = Path(repo)
    buckets = {}
    for root in config.get("scan_roots", DEFAULT_SCAN_ROOTS):
        base = repo / root
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*.md")):
            if not p.is_file():
                continue
            fm = parse_frontmatter(p)
            if not fm or "last_verified" not in fm:
                continue  # tracked notes only
            h = _normalized_hash(p.read_text())
            buckets.setdefault(h, []).append(p.relative_to(repo).as_posix())
    return [sorted(paths) for paths in buckets.values() if len(paths) > 1]


def commit_stamps(repo, paths, today, remote="origin", branch="main"):
    """Stamp each note to today; push the shared ones (not under private/) as one
    transaction. On a push conflict, reset to the remote tip and re-raise."""
    repo = Path(repo)
    shared = []
    for rel in paths:
        stamp(repo / rel, today)
        if Path(rel).parts[:1] != ("private",):
            shared.append(rel)
    if shared:
        try:
            push_paths(repo, "chore: re-verify notes (stamp last_verified)",
                       sorted(shared), remote=remote, branch=branch)
        except RuntimeError:
            run_git(repo, "reset", "--hard", f"{remote}/{branch}", check=False)
            raise
    return sorted(shared)
