# TTL / Freshness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the freshness/TTL subsystem: tracked notes carry `last_verified` front-matter, a session-start hook warns about stale/expired notes (pure date math), and an on-demand `/hive-audit` re-verifies + stamps + detects duplicates, committing shared stamps as a git transaction.

**Architecture:** Client-side, stdlib only. `lib/freshness.py` owns deterministic mechanics (read config, parse front-matter with a minimal scalar reader, compute status, scan, stamp, detect duplicates, commit stamps via `push_paths`). A thin `/hive-audit` skill supplies judgment. The session-start hook runs a fast, read-only date-math check as the final step of the non-blocked path. Config is `CONTROL/health.json`, read live.

**Tech Stack:** Python 3.11+ (stdlib: `datetime`, `hashlib`, `json`, `os`, `re`, `pathlib`), pytest, git via `lib/gitsync.py`.

**Spec:** `docs/superpowers/specs/2026-07-05-freshness-design.md`. Read it before starting; this plan implements sections 4.1-4.6.

**Branch:** work on `sp4-freshness` (already checked out). Land via PR at the end (main is branch-protected).

**Test command (from repo root):** `cd /Users/stas.wishnevetsky/team-brain-harness && ./.venv/bin/python -m pytest -q`.

---

## File Structure

**Create:**
- `lib/freshness.py` — `read_health_config`, `parse_frontmatter`, `note_status`, `scan`, `stamp`, `find_duplicates`, `commit_stamps`.
- `client-kit/skills/hive-audit/SKILL.md` — the thin audit skill (vendored into `CONTROL/skills/` by `instantiate`, delivered to clients by the SP3 skills mirror, same path pattern as `process-meeting`).
- `hive-template/CONTROL/health.json` — seeded horizons + scan roots.
- `hive-template/templates/knowledge-note.md` — the front-matter convention.
- `tests/test_freshness_unit.py`, `tests/test_freshness_integration.py`.

**Modify:**
- `client-kit/.claude/hooks/sync_pull.py` — after `roll_up_all` (final step of the non-blocked path), run the freshness check and print warnings.

**Reuse:** `lib/gitsync.py` `push_paths`, `run_git`.

---

## Conventions

- Tests use real git against `tmp_path`; reuse `tests/conftest.py` (`bare_remote`, `init_identity`).
- Import as `from lib.freshness import ...`. Stdlib only.
- Commit after each task; message ends with a blank line then:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- No em/en dashes.
- All date-dependent functions take `today` as a parameter (a `datetime.date`) for deterministic tests.

---

## Task 1: `read_health_config` + `parse_frontmatter`

**Files:** Create `lib/freshness.py`; Test `tests/test_freshness_unit.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_freshness_unit.py
from lib.freshness import read_health_config, parse_frontmatter, DEFAULT_SCAN_ROOTS

def test_read_health_config_default_when_missing(tmp_path):
    cfg = read_health_config(tmp_path)
    assert cfg["default_horizon_days"] == 180
    assert cfg["horizons"] == {}
    assert cfg["scan_roots"] == DEFAULT_SCAN_ROOTS
    assert "private" in cfg["scan_roots"]

def test_read_health_config_reads_file(tmp_path):
    import json
    (tmp_path / "CONTROL").mkdir()
    (tmp_path / "CONTROL" / "health.json").write_text(json.dumps(
        {"default_horizon_days": 90, "horizons": {"project": 30}, "scan_roots": ["engineering"]}))
    cfg = read_health_config(tmp_path)
    assert cfg["default_horizon_days"] == 90 and cfg["horizons"]["project"] == 30
    assert cfg["scan_roots"] == ["engineering"]

def test_parse_frontmatter_scalars_quotes_comments(tmp_path):
    f = tmp_path / "n.md"
    f.write_text('---\ntitle: "Adopt X"\ntype: decision\n'
                 'last_verified: 2026-07-05  # stamped\nreview_by: 2026-12-31\n---\nbody\n')
    fm = parse_frontmatter(f)
    assert fm["title"] == "Adopt X"
    assert fm["type"] == "decision"
    assert fm["last_verified"] == "2026-07-05"
    assert fm["review_by"] == "2026-12-31"

def test_parse_frontmatter_none_when_no_block(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("# Just a heading\nno front-matter\n")
    assert parse_frontmatter(f) is None

def test_parse_frontmatter_missing_last_verified(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("---\ntitle: x\ntype: reference\n---\nbody\n")
    fm = parse_frontmatter(f)
    assert fm is not None and "last_verified" not in fm
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
# lib/freshness.py
"""Freshness / TTL: track last_verified on notes, warn on staleness, re-verify
via the /hive-audit skill. Stdlib only. See
docs/superpowers/specs/2026-07-05-freshness-design.md."""
import json
import os
import re
from datetime import date
from pathlib import Path

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
        # strip an inline " # comment" (only when preceded by whitespace)
        m = re.search(r"\s+#", value)
        if m:
            value = value[:m.start()].strip()
        if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        if key:
            fm[key] = value
    return fm
```

- [ ] **Step 4: Run to verify it passes** (5 passed).
- [ ] **Step 5: Commit** (`feat: health config + minimal front-matter reader`).

---

## Task 2: `note_status` (pure date math)

**Files:** Modify `lib/freshness.py`; Test `tests/test_freshness_unit.py`.

**Context:** expired (review_by exclusive) > stale (`> horizon`, strict) > fresh. Untracked (no last_verified) returns None.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_freshness_unit.py
from datetime import date
from lib.freshness import note_status

CFG = {"default_horizon_days": 180, "horizons": {"project": 30, "decision": 365}}

def test_status_fresh_within_horizon():
    fm = {"type": "project", "last_verified": "2026-07-01"}
    assert note_status(fm, date(2026, 7, 05 if False else 5), CFG) == "fresh"

def test_status_stale_past_horizon():
    fm = {"type": "project", "last_verified": "2026-05-01"}  # >30d before today
    assert note_status(fm, date(2026, 7, 5), CFG) == "stale"

def test_status_horizon_boundary_is_strict():
    # exactly horizon days old -> still fresh (strictly greater is stale)
    fm = {"type": "project", "last_verified": "2026-06-05"}  # exactly 30 days
    assert note_status(fm, date(2026, 7, 5), CFG) == "fresh"

def test_status_uses_default_horizon_for_unknown_type():
    fm = {"type": "mystery", "last_verified": "2026-01-01"}  # >180d
    assert note_status(fm, date(2026, 7, 5), CFG) == "stale"

def test_status_expired_review_by_exclusive():
    fm = {"type": "decision", "last_verified": "2026-07-01", "review_by": "2026-07-05"}
    # on review_by day itself -> not yet expired
    assert note_status(fm, date(2026, 7, 5), CFG) == "fresh"
    # day after -> expired
    assert note_status(fm, date(2026, 7, 6), CFG) == "expired"

def test_status_untracked_when_no_last_verified():
    assert note_status({"type": "project"}, date(2026, 7, 5), CFG) is None
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
# add to lib/freshness.py
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
```

- [ ] **Step 4: Run to verify it passes** (fix the silly `05 if False else 5` in the first test to just `5` when you paste). Expected PASS.
- [ ] **Step 5: Commit** (`feat: note_status date math`).

---

## Task 3: `scan`

**Files:** Modify `lib/freshness.py`; Test `tests/test_freshness_unit.py`.

**Context:** walk each existing scan root (skip missing silently), parse front-matter, classify tracked notes only. Returns `[{path, type, status, last_verified, age_days}]` with `path` repo-relative (posix).

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_freshness_unit.py
from lib.freshness import scan

def _note(root, rel, lv, type_="reference", extra=""):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntype: {type_}\nlast_verified: {lv}\n{extra}---\nbody\n")

def test_scan_classifies_and_skips_untracked(tmp_path):
    cfg = {"default_horizon_days": 180, "horizons": {}, "scan_roots": ["engineering", "nope"]}
    _note(tmp_path, "engineering/fresh.md", "2026-07-01")
    _note(tmp_path, "engineering/stale.md", "2025-01-01")
    # untracked note (no last_verified) is ignored
    (tmp_path / "engineering" / "plain.md").write_text("# no frontmatter\n")
    results = scan(tmp_path, cfg, date(2026, 7, 5))
    by_path = {r["path"]: r for r in results}
    assert set(by_path) == {"engineering/fresh.md", "engineering/stale.md"}
    assert by_path["engineering/fresh.md"]["status"] == "fresh"
    assert by_path["engineering/stale.md"]["status"] == "stale"
    assert by_path["engineering/stale.md"]["age_days"] > 180

def test_scan_missing_root_is_silent(tmp_path):
    cfg = {"default_horizon_days": 180, "horizons": {}, "scan_roots": ["ghost"]}
    assert scan(tmp_path, cfg, date(2026, 7, 5)) == []
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
# add to lib/freshness.py
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
```

- [ ] **Step 4: Run to verify it passes** (2 passed).
- [ ] **Step 5: Commit** (`feat: scan tracked notes for freshness`).

---

## Task 4: `stamp` (atomic, byte-preserving, precondition-guarded)

**Files:** Modify `lib/freshness.py`; Test `tests/test_freshness_unit.py`.

**Context:** rewrite only the `last_verified:` line to `today`, atomically, preserving everything else. Precondition: the note has a front-matter block WITH a `last_verified:` line; otherwise raise `ValueError` (never silent no-op).

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_freshness_unit.py
import pytest
from lib.freshness import stamp

def test_stamp_updates_only_last_verified(tmp_path):
    f = tmp_path / "n.md"
    f.write_text('---\ntitle: "Keep Me"\ntype: decision\n'
                 'last_verified: 2025-01-01\nreview_by: 2026-12-31\n---\n# Keep Me\nbody line\n')
    stamp(f, date(2026, 7, 5))
    text = f.read_text()
    assert "last_verified: 2026-07-05" in text
    assert "2025-01-01" not in text
    # everything else preserved verbatim
    assert 'title: "Keep Me"' in text
    assert "review_by: 2026-12-31" in text
    assert "# Keep Me\nbody line\n" in text

def test_stamp_is_idempotent(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("---\ntype: reference\nlast_verified: 2026-07-05\n---\nbody\n")
    before = f.read_text()
    stamp(f, date(2026, 7, 5))
    assert f.read_text() == before  # same today -> no change

def test_stamp_raises_without_last_verified_line(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("---\ntype: reference\n---\nbody\n")
    with pytest.raises(ValueError):
        stamp(f, date(2026, 7, 5))
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
# add to lib/freshness.py
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
            break  # end of front-matter, no last_verified found
        if lines[i].split(":", 1)[0].strip() == "last_verified":
            eol = "\n" if lines[i].endswith("\n") else ""
            lines[i] = f"last_verified: {new_iso}{eol}"
            _atomic_write(path, "".join(lines))
            return
    raise ValueError(f"no last_verified line in front-matter: {path}")
```

- [ ] **Step 4: Run to verify it passes** (3 passed).
- [ ] **Step 5: Commit** (`feat: atomic byte-preserving stamp with precondition guard`).

---

## Task 5: `find_duplicates`

**Files:** Modify `lib/freshness.py`; Test `tests/test_freshness_unit.py`.

**Context:** cluster tracked notes whose normalized body (front-matter stripped, whitespace-collapsed, lowercased) hashes equal. Returns a list of clusters (each a sorted list of repo-relative paths), only clusters with 2+ members.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_freshness_unit.py
from lib.freshness import find_duplicates

def test_find_duplicates_clusters_near_identical(tmp_path):
    cfg = {"scan_roots": ["knowledge"], "default_horizon_days": 180, "horizons": {}}
    _note(tmp_path, "knowledge/a.md", "2026-07-01", extra="")  # body "body"
    _note(tmp_path, "knowledge/b.md", "2026-06-01", extra="")  # body "body" (dup, diff frontmatter)
    (tmp_path / "knowledge" / "c.md").write_text(
        "---\ntype: reference\nlast_verified: 2026-07-01\n---\ntotally different content\n")
    clusters = find_duplicates(tmp_path, cfg)
    assert clusters == [["knowledge/a.md", "knowledge/b.md"]]

def test_find_duplicates_none_when_all_distinct(tmp_path):
    cfg = {"scan_roots": ["knowledge"], "default_horizon_days": 180, "horizons": {}}
    (tmp_path / "knowledge").mkdir(parents=True)
    (tmp_path / "knowledge" / "a.md").write_text("---\nlast_verified: 2026-07-01\n---\nalpha\n")
    (tmp_path / "knowledge" / "b.md").write_text("---\nlast_verified: 2026-07-01\n---\nbeta\n")
    assert find_duplicates(tmp_path, cfg) == []
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
# add to lib/freshness.py
import hashlib

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
```

- [ ] **Step 4: Run to verify it passes** (2 passed). Then run the whole unit file.
- [ ] **Step 5: Commit** (`feat: deterministic near-duplicate detection`).

---

## Task 6: `commit_stamps` (stamp list + push shared as a transaction)

**Files:** Modify `lib/freshness.py`; Test `tests/test_freshness_integration.py`.

**Context:** the audit's mechanical step. Stamp each given repo-relative path to `today`; push the SHARED ones (not under `private/`) as one transaction via `push_paths`; `private/` stamps stay local (gitignored). On a push `RuntimeError`, reset --hard to the remote tip (reverts the shared stamps; private untouched since gitignored) and re-raise (surface to the user, do not swallow). Idempotent: re-stamping to the same `today` is an empty diff.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_freshness_integration.py
import subprocess
from datetime import date
from pathlib import Path
from lib.gitsync import run_git
from lib.freshness import commit_stamps
from tests.conftest import init_identity

def _clone(remote, dest):
    subprocess.run(["git", "clone", str(remote), str(dest)], check=True)
    init_identity(dest)
    return dest

def _tracked(repo, rel, lv):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntype: reference\nlast_verified: {lv}\n---\nbody\n")

def test_commit_stamps_pushes_shared_only(bare_remote, tmp_path):
    a = _clone(bare_remote, tmp_path / "a")
    _tracked(a, "engineering/adr.md", "2025-01-01")
    (a / "private" / "personal-context").mkdir(parents=True)
    _tracked(a, "private/personal-context/me.md", "2025-01-01")
    run_git(a, "add", "engineering"); run_git(a, "commit", "-m", "seed note")
    run_git(a, "push", "origin", "main")

    shared = commit_stamps(a, ["engineering/adr.md", "private/personal-context/me.md"],
                           date(2026, 7, 5))
    assert shared == ["engineering/adr.md"]
    # shared stamp reached the remote
    v = _clone(bare_remote, tmp_path / "v")
    assert "last_verified: 2026-07-05" in (v / "engineering" / "adr.md").read_text()
    # private stamp stayed local (never pushed; the file is gitignored on a real client,
    # here we assert it is not in the fresh clone)
    assert not (v / "private").exists()

def test_commit_stamps_push_conflict_propagates_and_resets(bare_remote, tmp_path, monkeypatch):
    a = _clone(bare_remote, tmp_path / "a")
    _tracked(a, "engineering/adr.md", "2025-01-01")
    run_git(a, "add", "engineering"); run_git(a, "commit", "-m", "seed"); run_git(a, "push", "origin", "main")
    import lib.freshness as fr
    monkeypatch.setattr(fr, "push_paths",
                        lambda *args, **kw: (_ for _ in ()).throw(RuntimeError("conflict")))
    import pytest
    with pytest.raises(RuntimeError):
        commit_stamps(a, ["engineering/adr.md"], date(2026, 7, 5))
    # repo left clean at the remote tip; the shared stamp was reverted
    assert run_git(a, "status", "--porcelain").stdout.strip() == ""
    assert "last_verified: 2025-01-01" in (a / "engineering" / "adr.md").read_text()
```

- [ ] **Step 2: Run to verify it fails** (ImportError on commit_stamps).

- [ ] **Step 3: Implement**

```python
# add to lib/freshness.py  (add this import near the top with the others)
from lib.gitsync import run_git, push_paths

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
```

- [ ] **Step 4: Run to verify it passes** (2 passed), then the whole suite.
- [ ] **Step 5: Commit** (`feat: commit_stamps transaction (push shared, reset+raise on conflict)`).

---

## Task 7: hook wiring (session-start freshness check)

**Files:** Modify `client-kit/.claude/hooks/sync_pull.py`; Test `tests/test_freshness_integration.py`.

**Context:** after `roll_up_all` (final step of the non-blocked path), scan and print a read-only summary. A gated client returns before this (unchanged). Add a small helper so the hook stays thin and is testable.

- [ ] **Step 1: Write the failing test** (drive a `freshness_report` helper the hook will call)

```python
# add to tests/test_freshness_integration.py
from lib.freshness import freshness_report

def test_freshness_report_lists_stale_and_expired(tmp_path):
    cfg_dir = tmp_path / "CONTROL"; cfg_dir.mkdir()
    import json
    (cfg_dir / "health.json").write_text(json.dumps(
        {"default_horizon_days": 180, "horizons": {}, "scan_roots": ["engineering"]}))
    _tracked(tmp_path, "engineering/old.md", "2025-01-01")  # stale
    lines = freshness_report(tmp_path, date(2026, 7, 5))
    assert any("freshness:" in ln and "stale" in ln for ln in lines)
    assert any("engineering/old.md" in ln for ln in lines)

def test_freshness_report_empty_when_all_fresh(tmp_path):
    import json
    (tmp_path / "CONTROL").mkdir()
    (tmp_path / "CONTROL" / "health.json").write_text(json.dumps(
        {"default_horizon_days": 180, "horizons": {}, "scan_roots": ["engineering"]}))
    _tracked(tmp_path, "engineering/new.md", "2026-07-01")
    assert freshness_report(tmp_path, date(2026, 7, 5)) == []
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement the helper** (add to `lib/freshness.py`)

```python
def freshness_report(repo, today):
    """Read-only. Return a list of report lines (empty if nothing stale/expired)."""
    cfg = read_health_config(repo)
    results = scan(repo, cfg, today)
    flagged = [r for r in results if r["status"] in ("stale", "expired")]
    if not flagged:
        return []
    n_stale = sum(1 for r in flagged if r["status"] == "stale")
    n_exp = sum(1 for r in flagged if r["status"] == "expired")
    lines = [f"freshness: {n_stale} stale, {n_exp} expired  (run /hive-audit to re-verify)"]
    for r in sorted(flagged, key=lambda r: r["path"]):
        if r["status"] == "stale":
            lines.append(f"  STALE   {r['path']}  (verified {r['age_days']}d ago)")
        else:
            lines.append(f"  EXPIRED {r['path']}")
    return lines
```

- [ ] **Step 4: Wire the hook** — in `client-kit/.claude/hooks/sync_pull.py`, add the import and call `freshness_report` as the final step of `main()` (after the `roll_up_all` loop). Update the imports block to:

```python
from lib.gitsync import pull
from lib.control_plane import apply_control_plane
from lib.meeting_rollup import roll_up_all
from lib.freshness import freshness_report
```

And append to the END of `main()` (after the `for name, status in roll_up_all(...)` loop, still inside `main`, only reached on the non-blocked path):

```python
    from datetime import date
    for line in freshness_report(a.repo, date.today()):
        print(line)
```

(Do not move it above the `if cp["blocked"]: return` block; it must stay after, so a gated client skips it.)

- [ ] **Step 5: Run the whole suite** — confirm all pass, including that the existing `test_rollup_e2e.py` / control-plane tests still pass (the hook now prints freshness lines but the seeded template notes are all fresh or absent, so no behavioral break).
- [ ] **Step 6: Commit** (`feat: session-start freshness check in the hook`).

---

## Task 8: `/hive-audit` skill + config + template + e2e + docs

**Files:** Create `client-kit/skills/hive-audit/SKILL.md`, `hive-template/CONTROL/health.json`, `hive-template/templates/knowledge-note.md`; create `tests/test_freshness_e2e.py`; modify `README.md`, `docs/getting-started.md`.

- [ ] **Step 1: Create `hive-template/CONTROL/health.json`**

```json
{
  "default_horizon_days": 180,
  "horizons": {"reference": 180, "project": 30, "decision": 365, "knowledge": 180},
  "scan_roots": ["org", "product", "engineering", "design", "customers", "market", "knowledge", "projects", "decisions", "private"]
}
```

- [ ] **Step 2: Create `hive-template/templates/knowledge-note.md`**

```markdown
---
title: Short title
type: knowledge
last_verified: 2026-01-01
# review_by: 2026-12-31   # optional hard expiry
---
# Short title

Body. Set `type` to one of the configured horizons (reference, project, decision, knowledge, ...).
Re-run /hive-audit to re-confirm this note and bump last_verified.
```

- [ ] **Step 3: Create `client-kit/skills/hive-audit/SKILL.md`**

```markdown
---
name: hive-audit
description: Re-verify stale/expired notes (stamp the ones still true), and surface near-duplicates. On-demand freshness maintenance for the shared hive.
---

# Hive audit

On-demand freshness pass over tracked notes (those with `last_verified` front-matter).

## Steps

1. **Find stale/expired notes:**
   ```python
   from datetime import date
   from lib.freshness import read_health_config, scan
   cfg = read_health_config("<repo>")
   [r for r in scan("<repo>", cfg, date.today()) if r["status"] in ("stale", "expired")]
   ```

2. **Re-verify each against current knowledge / live data.** For each stale or expired note, read it and judge: is it still true?
   - **Still true** -> keep it in a `to_stamp` list.
   - **No longer true** -> do NOT stamp. Surface it to the user with a proposed rewrite or deletion. Never auto-rewrite or auto-delete shared knowledge.

3. **Stamp + commit the confirmed notes** (one transaction; private stamps stay local):
   ```python
   from lib.freshness import commit_stamps
   commit_stamps("<repo>", to_stamp, date.today())
   ```
   If it raises (a concurrent push conflict), tell the user the stamp did not land and to re-run; the repo is left clean.

4. **Surface duplicates** (do not auto-merge; merging shared notes is destructive):
   ```python
   from lib.freshness import find_duplicates
   find_duplicates("<repo>", cfg)
   ```
   Report each cluster to the user and propose a merge for them to confirm.
```

- [ ] **Step 4: Write the e2e test** `tests/test_freshness_e2e.py`

```python
import subprocess, sys
from datetime import date
from pathlib import Path
from tools.instantiate import instantiate
from tools.setup_client import setup_client
from lib.gitsync import run_git
from lib.freshness import commit_stamps

def _bare_from(local, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def test_stale_note_flagged_then_stamped_seen_fresh(tmp_path):
    hive = instantiate(tmp_path / "hive")
    # admin adds an old tracked note to a shared dir and pushes
    (hive / "engineering" / "adr-001.md").write_text(
        "---\ntype: decision\nlast_verified: 2020-01-01\n---\n# old\n")
    run_git(hive, "add", "-A"); run_git(hive, "commit", "-m", "old note")
    remote = _bare_from(hive, tmp_path)
    client = setup_client(str(remote), tmp_path / "client")

    # session-start hook flags it stale
    r = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "STALE" in r.stdout and "engineering/adr-001.md" in r.stdout

    # audit's mechanical step: stamp + push (use a fixed today so it lands fresh)
    commit_stamps(client, ["engineering/adr-001.md"], date.today())

    # a second client pulls and no longer sees it stale
    client2 = setup_client(str(remote), tmp_path / "client2")
    r2 = subprocess.run(
        [sys.executable, str(client2 / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client2)], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert "engineering/adr-001.md" not in r2.stdout
```

- [ ] **Step 5: Run the e2e + full suite.** Debug until green. (Note: `instantiate` copies `client-kit/skills` -> `CONTROL/skills`, so `hive-audit` is vendored; `setup_client`'s `sync_skills` materializes it. `health.json` ships in the template so `read_health_config` reads real horizons.)

- [ ] **Step 6: Docs**
- `README.md`: bump status badge to `4/5 sub-projects`; bump the tests badge to the new count (run the suite, use the final number); add a "Freshness" bullet under How it works (notes carry last_verified; session start warns about stale/expired; /hive-audit re-verifies + stamps); update the Status section to list sub-projects 1-4 done, 5 (installer/onboarding) remaining.
- `docs/getting-started.md`: add a "Keeping knowledge fresh" subsection (write notes from `templates/knowledge-note.md` with `last_verified`; the session-start check warns; run `/hive-audit` to re-verify); add command-reference rows: "Re-verify stale notes" -> "run the `/hive-audit` skill"; note that horizons live in `CONTROL/health.json`.

- [ ] **Step 7: Run the full suite + commit** (`feat: /hive-audit skill + health config + knowledge-note template; test: freshness e2e; docs: mark sub-project 4 shipped`).

---

## Final: after all tasks

- [ ] Run the full suite once more: `cd /Users/stas.wishnevetsky/team-brain-harness && ./.venv/bin/python -m pytest -q` (all green).
- [ ] Use **superpowers:finishing-a-development-branch**. Given `main` is branch-protected, the expected path is **Option 1 (push and open a PR)** for your own review/merge.
