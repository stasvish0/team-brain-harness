# Control Plane + Client Update Mechanism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the client-side control plane so an admin can edit `CONTROL/` and push, and every client converges on the next session-start pull (structure migrations, skills mirror, policy, MCP announcements), gating safely when too old, plus an admin purge tool.

**Architecture:** All client-side, stdlib only. A new `lib/control_plane.py` reads `CONTROL/manifest.json`, compares it to a client-local `.applied.json`, evaluates a version gate, and on a clear gate applies changes in order: structure migrations (declarative JSON ops, committed + pushed as a git transaction via `push_paths`), a full-mirror skills sync into the gitignored `.claude/skills/`, a policy reload, and MCP announcements. A gate safe-halts (apply nothing, write `.control-block`, skip roll-up). `tools/purge.py` scrubs a leaked path from all history. The SessionStart hook runs the control plane between `pull` and `roll_up_all`.

**Tech Stack:** Python 3.11+ (stdlib: `json`, `os`, `shutil`, `pathlib`, `subprocess`), pytest, git via `lib/gitsync.py`.

**Spec:** `docs/superpowers/specs/2026-07-05-control-plane-design.md`. Read it before starting; this plan implements sections 4.1-4.10.

**Branch:** work on `sp3-control-plane` (already checked out). Land via PR at the end (main is branch-protected).

**Test command (from repo root):** `./.venv/bin/python -m pytest -q`. IMPORTANT: run from `/Users/stas.wishnevetsky/team-brain-harness` (pytest rootdir must be the repo, not a parent).

---

## File Structure

**Create:**
- `lib/version.py` — `CLIENT_VERSION` constant (the client's own version, travels with vendored `lib/`).
- `lib/control_plane.py` — the reconciliation engine: `version_tuple`, `read_manifest`, `read_applied`, `write_applied` (atomic), `pending_migrations`, `evaluate_gate`, `apply_migration` (declarative ops + containment, returns touched paths), `sync_skills`, `reload_policy`, `mcp_announcements`, `apply_control_plane` (orchestrator).
- `tools/purge.py` — admin history-scrub tool.
- `hive-template/CONTROL/policy.md` — standing instructions (seeded content incl. the block clause).
- `hive-template/CONTROL/migrations/.gitkeep`, `hive-template/CONTROL/skills/.gitkeep`.
- `tests/test_control_plane_unit.py`, `tests/test_control_plane_integration.py`, `tests/test_purge.py`, `tests/test_control_plane_e2e.py`.

**Modify:**
- `hive-template/.gitignore` — add `/.applied.json` and `/.control-block`.
- `tools/setup_client.py` — seed `.applied.json`, run initial `sync_skills`, add the two files to `.git/info/exclude`.
- `client-kit/.claude/hooks/sync_pull.py` — run `apply_control_plane` between `pull` and `roll_up_all`; print summary / BLOCKED notice.
- **Relocate** `client-kit/.claude/skills/process-meeting/` -> `client-kit/skills/process-meeting/` (so `instantiate` vendors it into `CONTROL/skills/` and it reaches clients via the mirror). `tools/instantiate.py` needs no code change (it already vendors `client-kit/skills/` -> `CONTROL/skills/`).

**Do NOT touch:** `lib/gitsync.py` (reuse `pull`, `push_paths`, `run_git`, `read_allowlist` as-is), `lib/meeting_rollup.py`.

---

## Conventions

- Tests use real git against `tmp_path`; reuse `tests/conftest.py`'s `bare_remote` fixture and `init_identity` / `_git` helpers.
- Import as `from lib.control_plane import ...`, `from lib.version import CLIENT_VERSION`.
- Stdlib only. Commit after each task; end every commit message with a blank line then:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- No em/en dashes.

---

## Task 1: `lib/version.py` + `version_tuple`

**Files:** Create `lib/version.py`, `lib/control_plane.py`; Test `tests/test_control_plane_unit.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_control_plane_unit.py
from lib.version import CLIENT_VERSION
from lib.control_plane import version_tuple

def test_client_version_is_a_dotted_string():
    assert isinstance(CLIENT_VERSION, str)
    assert version_tuple(CLIENT_VERSION)  # parses without error

def test_version_tuple_orders_correctly():
    assert version_tuple("0.0.1") < version_tuple("0.1.0")
    assert version_tuple("1.2.3") == version_tuple("1.2.3")
    assert version_tuple("0.10.0") > version_tuple("0.9.0")
```

- [ ] **Step 2: Run to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_control_plane_unit.py -q`
Expected: FAIL (ImportError).

- [ ] **Step 3: Implement**

```python
# lib/version.py
CLIENT_VERSION = "0.0.1"
```

```python
# lib/control_plane.py
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
```

- [ ] **Step 4: Run to verify it passes** (3 passed).
- [ ] **Step 5: Commit**

```bash
git add lib/version.py lib/control_plane.py tests/test_control_plane_unit.py
git commit -m "feat: client version + version_tuple for control plane

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: manifest + `.applied.json` I/O (atomic write, default-when-missing)

**Files:** Modify `lib/control_plane.py`; Test `tests/test_control_plane_unit.py`.

**Context:** `read_applied` returns a zeroed default when the file is missing. `write_applied` and `.control-block` writes are atomic (temp file + `os.replace`) so a crash never corrupts them.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_control_plane_unit.py
import json
from lib.control_plane import read_manifest, read_applied, write_applied, DEFAULT_APPLIED

def test_read_applied_defaults_when_missing(tmp_path):
    assert read_applied(tmp_path) == DEFAULT_APPLIED

def test_write_then_read_applied_roundtrips(tmp_path):
    applied = {"skills_version": 2, "structure_version": 3,
               "policy_version": 1, "announced_mcps": ["granola"]}
    write_applied(tmp_path, applied)
    assert read_applied(tmp_path) == applied

def test_read_manifest_reads_control_manifest(tmp_path):
    (tmp_path / "CONTROL").mkdir()
    (tmp_path / "CONTROL" / "manifest.json").write_text(
        json.dumps({"skills_version": 1, "structure_version": 0,
                    "min_client_version": "0.0.1", "required_mcps": [],
                    "policy_version": 1}))
    m = read_manifest(tmp_path)
    assert m["skills_version"] == 1 and m["min_client_version"] == "0.0.1"

def test_write_applied_is_atomic_on_crash(tmp_path, monkeypatch):
    # pre-seed a valid file, then make the replace step fail mid-write
    good = {"skills_version": 1, "structure_version": 1,
            "policy_version": 1, "announced_mcps": []}
    write_applied(tmp_path, good)
    import lib.control_plane as cp
    monkeypatch.setattr(cp.os, "replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    try:
        write_applied(tmp_path, {"skills_version": 99})
    except OSError:
        pass
    # the original file survived intact (temp-file + replace never clobbered it)
    assert read_applied(tmp_path) == good
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement** (add to `lib/control_plane.py`)

```python
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
```

- [ ] **Step 4: Run to verify it passes** (3 passed).
- [ ] **Step 5: Commit** (`feat: manifest + atomic .applied.json IO`).

---

## Task 3: declarative migrations (ops + containment + touched paths + pending)

**Files:** Modify `lib/control_plane.py`; Test `tests/test_control_plane_unit.py`.

**Context:** `apply_migration(repo, migration)` interprets ops idempotently and returns the set of repo-relative paths touched. Path containment rejects `..`, absolute paths, symlink-escape, and any target under `private/`, `.claude/`, `.git/`. `pending_migrations(repo, applied)` returns `[{"id": int, "path": Path, "data": dict}, ...]` for migrations with `id > applied["structure_version"]`, sorted by id.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_control_plane_unit.py
import pytest
from lib.control_plane import apply_migration, pending_migrations

def test_make_dir_and_keep_file_idempotent(tmp_path):
    mig = {"ops": [{"op": "make_dir", "path": "legal"},
                   {"op": "keep_file", "path": "legal/.gitkeep"}]}
    touched = apply_migration(tmp_path, mig)
    assert (tmp_path / "legal" / ".gitkeep").exists()
    assert "legal/.gitkeep" in touched
    # second run: already in target state -> no touched paths
    assert apply_migration(tmp_path, mig) == set()

def test_move_quadrants(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "a" / "f.md").write_text("x\n")
    mig = {"ops": [{"op": "move", "from": "a/f.md", "to": "b/f.md"}]}
    touched = apply_migration(tmp_path, mig)
    assert not (tmp_path / "a" / "f.md").exists()
    assert (tmp_path / "b" / "f.md").exists()
    assert touched == {"a/f.md", "b/f.md"}
    # from absent, to exists -> no-op (idempotent second run)
    assert apply_migration(tmp_path, mig) == set()

def test_move_collision_raises(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "a" / "f").write_text("1")
    (tmp_path / "b").mkdir(); (tmp_path / "b" / "f").write_text("2")
    with pytest.raises(ValueError):
        apply_migration(tmp_path, {"ops": [{"op": "move", "from": "a/f", "to": "b/f"}]})

def test_delete_idempotent(tmp_path):
    (tmp_path / "d").mkdir(); (tmp_path / "d" / "x").write_text("x")
    assert apply_migration(tmp_path, {"ops": [{"op": "delete", "path": "d/x"}]}) == {"d/x"}
    assert apply_migration(tmp_path, {"ops": [{"op": "delete", "path": "d/x"}]}) == set()

@pytest.mark.parametrize("bad", ["../escape", "/abs/path", "private/x", ".claude/x", ".git/x"])
def test_path_containment_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        apply_migration(tmp_path, {"ops": [{"op": "make_dir", "path": bad}]})

def test_pending_migrations_filters_and_sorts(tmp_path):
    md = tmp_path / "CONTROL" / "migrations"; md.mkdir(parents=True)
    (md / "0001-a.json").write_text('{"ops": []}')
    (md / "0002-b.json").write_text('{"ops": []}')
    (md / "0003-c.json").write_text('{"ops": []}')
    pend = pending_migrations(tmp_path, {"structure_version": 1})
    assert [p["id"] for p in pend] == [2, 3]
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement** (add to `lib/control_plane.py`)

```python
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
    return repo / relpath  # unresolved form for actual fs ops

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
            # (from absent) -> no-op, whether or not dst exists
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
            continue  # skip mis-named files rather than crashing the session
        if mid > applied.get("structure_version", 0):
            out.append({"id": mid, "path": p, "data": json.loads(p.read_text())})
    return sorted(out, key=lambda m: m["id"])
```

- [ ] **Step 4: Run to verify it passes** (all Task 3 tests pass).
- [ ] **Step 5: Commit** (`feat: declarative idempotent migration ops + pending discovery`).

---

## Task 4: `evaluate_gate`

**Files:** Modify `lib/control_plane.py`; Test `tests/test_control_plane_unit.py`.

**Context:** gate reasons = `client < manifest.min_client_version`, plus `client < m.min_client_version` for any pending migration `m` that declares one. Empty list = clear.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_control_plane_unit.py
from lib.control_plane import evaluate_gate

def _man(minv="0.0.1"):
    return {"min_client_version": minv}

def test_gate_clear_when_client_current():
    assert evaluate_gate(_man("0.0.1"), "0.0.1", []) == []

def test_gate_blocks_when_client_older_than_manifest():
    assert evaluate_gate(_man("0.1.0"), "0.0.1", []) != []

def test_gate_blocks_on_pending_migration_min_version():
    pend = [{"min_client_version": "0.2.0"}]
    assert evaluate_gate(_man("0.0.1"), "0.0.1", pend) != []

def test_gate_clear_when_client_meets_migration_min():
    pend = [{"min_client_version": "0.2.0"}, {"min_client_version": None}]
    assert evaluate_gate(_man("0.0.1"), "0.2.0", pend) == []
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
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
```

- [ ] **Step 4: Run to verify it passes** (4 passed).
- [ ] **Step 5: Commit** (`feat: control-plane version gate`).

---

## Task 5: `sync_skills` (full mirror)

**Files:** Modify `lib/control_plane.py`; Test `tests/test_control_plane_unit.py`.

**Context:** mirror `CONTROL/skills/` -> `.claude/skills/` (add/update/delete). Never touches `.claude/skills-local/`. Returns `{"added": n, "updated": n, "deleted": n}`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_control_plane_unit.py
from lib.control_plane import sync_skills

def _skill(root, name, body):
    d = root / "CONTROL" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body)

def test_sync_skills_adds_updates_deletes(tmp_path):
    _skill(tmp_path, "alpha", "A1")
    _skill(tmp_path, "beta", "B1")
    r1 = sync_skills(tmp_path)
    assert (tmp_path / ".claude" / "skills" / "alpha" / "SKILL.md").read_text() == "A1"
    assert r1["added"] == 2
    # update alpha, remove beta from CONTROL
    _skill(tmp_path, "alpha", "A2")
    shutil.rmtree(tmp_path / "CONTROL" / "skills" / "beta")
    r2 = sync_skills(tmp_path)
    assert (tmp_path / ".claude" / "skills" / "alpha" / "SKILL.md").read_text() == "A2"
    assert not (tmp_path / ".claude" / "skills" / "beta").exists()
    assert r2["updated"] == 1 and r2["deleted"] == 1

def test_sync_skills_leaves_skills_local_untouched(tmp_path):
    _skill(tmp_path, "alpha", "A1")
    local = tmp_path / ".claude" / "skills-local" / "mine"
    local.mkdir(parents=True); (local / "SKILL.md").write_text("MINE")
    sync_skills(tmp_path)
    assert (local / "SKILL.md").read_text() == "MINE"
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
import shutil  # already imported at top; ensure present

def sync_skills(repo):
    repo = Path(repo)
    src = repo / "CONTROL" / "skills"
    dst = repo / ".claude" / "skills"
    src.mkdir(parents=True, exist_ok=True)
    dst.mkdir(parents=True, exist_ok=True)
    src_files = {p.relative_to(src) for p in src.rglob("*") if p.is_file()}
    dst_files = {p.relative_to(dst) for p in dst.rglob("*") if p.is_file()}
    added = updated = deleted = 0
    for rel in sorted(src_files):
        s, d = src / rel, dst / rel
        if not d.exists():
            added += 1
        elif s.read_bytes() != d.read_bytes():
            updated += 1
        else:
            continue
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d)
    for rel in sorted(dst_files - src_files):
        (dst / rel).unlink()
        deleted += 1
    return {"added": added, "updated": updated, "deleted": deleted}
```

- [ ] **Step 4: Run to verify it passes** (2 passed).
- [ ] **Step 5: Commit** (`feat: full-mirror skills sync`).

---

## Task 6: `reload_policy` + `mcp_announcements`

**Files:** Modify `lib/control_plane.py`; Test `tests/test_control_plane_unit.py`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_control_plane_unit.py
from lib.control_plane import reload_policy, mcp_announcements

def test_reload_policy_reads_or_empty(tmp_path):
    assert reload_policy(tmp_path) == ""
    (tmp_path / "CONTROL").mkdir(exist_ok=True)
    (tmp_path / "CONTROL" / "policy.md").write_text("be excellent\n")
    assert reload_policy(tmp_path) == "be excellent\n"

def test_mcp_announcements_only_new():
    manifest = {"required_mcps": [{"name": "granola", "how": "auth in settings"},
                                  {"name": "jira", "how": "oauth"}]}
    applied = {"announced_mcps": ["granola"]}
    out = mcp_announcements(manifest, applied)
    assert [m["name"] for m in out] == ["jira"]
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
def reload_policy(repo):
    p = Path(repo) / "CONTROL" / "policy.md"
    return p.read_text() if p.exists() else ""

def mcp_announcements(manifest, applied):
    announced = set(applied.get("announced_mcps", []))
    return [m for m in manifest.get("required_mcps", []) if m["name"] not in announced]
```

- [ ] **Step 4: Run to verify it passes** (2 passed).
- [ ] **Step 5: Commit** (`feat: policy reload + MCP announcement diff`).

---

## Task 7: `apply_control_plane` orchestrator (the transaction)

**Files:** Modify `lib/control_plane.py`; Test `tests/test_control_plane_integration.py`.

**Context:** ties it together against a real git repo. Order per spec 4.3: read manifest/applied/CLIENT_VERSION; compute pending; evaluate gate; if gated -> write `.control-block`, return `{"blocked": True, ...}`, apply nothing. Else remove stale `.control-block` and apply: (1) each pending migration -> apply ops, verify touched paths are inside the publish allowlist (else gate as malformed), if touched commit+push EXACTLY those paths via `push_paths`; on `RuntimeError` reset --hard to remote tip and stop (defer, do not advance); advance `applied.structure_version` per migration via atomic write; (2) skills mirror if `skills_version` differs; (3) policy reload if `policy_version` differs; (4) MCP announcements. Returns a result dict.

**Allowlist check:** read the client's `publish_allowlist.txt` via `lib.gitsync.read_allowlist`; a touched path is allowed if it starts with any allowlist entry (entries are dir prefixes like `CONTROL/`, `engineering/`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_control_plane_integration.py
import json, subprocess
from pathlib import Path
from lib.gitsync import run_git, push_paths
from lib.control_plane import apply_control_plane, read_applied
from tests.conftest import init_identity

def _hive(bare_remote, tmp_path, name, manifest, allowlist="CONTROL/\nengineering/\n"):
    d = tmp_path / name
    subprocess.run(["git", "clone", str(bare_remote), str(d)], check=True)
    init_identity(d)
    (d / "CONTROL").mkdir(exist_ok=True)
    (d / "CONTROL" / "manifest.json").write_text(json.dumps(manifest))
    (d / "publish_allowlist.txt").write_text(allowlist)
    return d

def _manifest(**over):
    m = {"skills_version": 0, "structure_version": 0, "min_client_version": "0.0.1",
         "required_mcps": [], "policy_version": 0}
    m.update(over); return m

def test_gated_session_applies_nothing_and_writes_block(bare_remote, tmp_path):
    d = _hive(bare_remote, tmp_path, "c", _manifest(min_client_version="9.9.9"))
    res = apply_control_plane(d)
    assert res["blocked"] is True and res["gate_reasons"]
    assert (d / ".control-block").exists()

def test_migration_applied_committed_and_pushed(bare_remote, tmp_path):
    d = _hive(bare_remote, tmp_path, "c", _manifest(structure_version=1))
    md = d / "CONTROL" / "migrations"; md.mkdir(parents=True)
    (md / "0001-add-eng.json").write_text(json.dumps(
        {"ops": [{"op": "make_dir", "path": "engineering/adr"},
                 {"op": "keep_file", "path": "engineering/adr/.gitkeep"}]}))
    run_git(d, "add", "-A"); run_git(d, "commit", "-m", "seed migration")
    run_git(d, "push", "origin", "main")
    res = apply_control_plane(d)
    assert res["blocked"] is False
    assert (d / "engineering" / "adr" / ".gitkeep").exists()
    assert read_applied(d)["structure_version"] == 1
    # the change reached the remote
    verify = tmp_path / "verify"
    subprocess.run(["git", "clone", str(bare_remote), str(verify)], check=True)
    assert (verify / "engineering" / "adr" / ".gitkeep").exists()

def test_second_client_noops_already_migrated_tree(bare_remote, tmp_path):
    # first client applies + pushes
    d = _hive(bare_remote, tmp_path, "c", _manifest(structure_version=1))
    md = d / "CONTROL" / "migrations"; md.mkdir(parents=True)
    (md / "0001-add-eng.json").write_text(json.dumps(
        {"ops": [{"op": "keep_file", "path": "engineering/adr/.gitkeep"}]}))
    run_git(d, "add", "-A"); run_git(d, "commit", "-m", "seed"); run_git(d, "push", "origin", "main")
    apply_control_plane(d)
    # second client pulls the migrated tree, applies -> empty diff, no error
    d2 = tmp_path / "c2"
    subprocess.run(["git", "clone", str(bare_remote), str(d2)], check=True)
    init_identity(d2)
    (d2 / "publish_allowlist.txt").write_text("CONTROL/\nengineering/\n")
    res = apply_control_plane(d2)
    assert res["blocked"] is False
    assert read_applied(d2)["structure_version"] == 1

def test_skills_and_mcp_and_policy_applied(bare_remote, tmp_path):
    d = _hive(bare_remote, tmp_path, "c",
              _manifest(skills_version=1, policy_version=1,
                        required_mcps=[{"name": "granola", "how": "auth in settings"}]))
    sk = d / "CONTROL" / "skills" / "demo"; sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("demo")
    (d / "CONTROL" / "policy.md").write_text("standing rules\n")
    res = apply_control_plane(d)
    assert (d / ".claude" / "skills" / "demo" / "SKILL.md").exists()
    assert [m["name"] for m in res["mcp_announcements"]] == ["granola"]
    assert "standing rules" in res["policy_text"]
    ap = read_applied(d)
    assert ap["skills_version"] == 1 and ap["policy_version"] == 1
    assert ap["announced_mcps"] == ["granola"]
    # second run: nothing new
    res2 = apply_control_plane(d)
    assert res2["mcp_announcements"] == []
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement** (add to `lib/control_plane.py`; note the new imports)

```python
from lib.gitsync import run_git, push_paths, read_allowlist
from lib.version import CLIENT_VERSION

def _allowlisted(touched, allow_paths):
    for t in touched:
        if not any(t == a.rstrip("/") or t.startswith(a) for a in allow_paths):
            return False
    return True

def apply_control_plane(repo, remote="origin", branch="main"):
    repo = Path(repo)
    manifest = read_manifest(repo)
    applied = read_applied(repo)
    pend = pending_migrations(repo, applied)
    result = {"blocked": False, "gate_reasons": [], "migrations_applied": [],
              "skills_changed": None, "policy_text": "", "mcp_announcements": [],
              "deferred": False}
    # Load policy up front so it is emitted even on the gated early-return (the
    # block clause telling the assistant to stop matters most exactly when gated).
    result["policy_text"] = reload_policy(repo)
    reasons = evaluate_gate(manifest, CLIENT_VERSION, [m["data"] for m in pend])
    block = repo / ".control-block"
    if reasons:
        _atomic_write(block, "\n".join(reasons) + "\n")
        result["blocked"] = True
        result["gate_reasons"] = reasons
        return result
    if block.exists():
        block.unlink()

    allow = []
    al = repo / "publish_allowlist.txt"
    if al.exists():
        allow = read_allowlist(al)

    # 1. structure migrations (in order)
    for m in pend:
        touched = apply_migration(repo, m["data"])
        if touched and not _allowlisted(touched, allow):
            # malformed: would push an unshareable path -> gate
            _atomic_write(block, f"migration {m['path'].name} touches non-allowlisted path\n")
            run_git(repo, "reset", "--hard", f"{remote}/{branch}", check=False)
            result["blocked"] = True
            result["gate_reasons"] = [f"migration {m['path'].name} touches non-allowlisted path"]
            return result
        if touched:
            try:
                push_paths(repo, f"migrate: {m['path'].name}", sorted(touched),
                           remote=remote, branch=branch)
            except RuntimeError:
                run_git(repo, "reset", "--hard", f"{remote}/{branch}", check=False)
                result["deferred"] = True
                return result  # retry next session; do not advance
        applied["structure_version"] = m["id"]
        write_applied(repo, applied)
        result["migrations_applied"].append(m["path"].name)

    # 2. skills mirror
    if manifest.get("skills_version", 0) != applied.get("skills_version", 0):
        result["skills_changed"] = sync_skills(repo)
        applied["skills_version"] = manifest.get("skills_version", 0)
        write_applied(repo, applied)

    # 3. policy reload (policy_text already loaded at the top)
    if manifest.get("policy_version", 0) != applied.get("policy_version", 0):
        applied["policy_version"] = manifest.get("policy_version", 0)
        write_applied(repo, applied)

    # 4. MCP announcements
    result["mcp_announcements"] = mcp_announcements(manifest, applied)
    if result["mcp_announcements"]:
        applied["announced_mcps"] = list(applied.get("announced_mcps", [])) + \
            [m["name"] for m in result["mcp_announcements"]]
        write_applied(repo, applied)
    return result
```

- [ ] **Step 4: Run to verify it passes** (all Task 7 tests pass; then run the whole suite).
- [ ] **Step 5: Commit** (`feat: apply_control_plane orchestrator (gate, migration txn, skills, policy, mcp)`).

---

## Task 8: hook wiring + template + setup_client + relocate skill

**Files:**
- Modify `client-kit/.claude/hooks/sync_pull.py`
- Modify `tools/setup_client.py`
- Modify `hive-template/.gitignore`
- Create `hive-template/CONTROL/policy.md`, `hive-template/CONTROL/migrations/.gitkeep`, `hive-template/CONTROL/skills/.gitkeep`
- Move `client-kit/.claude/skills/process-meeting/` -> `client-kit/skills/process-meeting/`
- Test: `tests/test_control_plane_integration.py`

- [ ] **Step 1: Relocate the skill and add template files**

```bash
git mv client-kit/.claude/skills/process-meeting client-kit/skills/process-meeting
# remove the now-empty client-kit/.claude/skills dir if git leaves it (it won't track empty dirs)
printf '# Team policy (standing instructions)\n\nThese instructions are loaded into every session.\n\n- If a `.control-block` file exists at the repo root, the client is gated: refuse substantive shared-vault work (no publishing, no roll-up authoring) until it clears. Tell the user to update per the BLOCKED notice.\n' > hive-template/CONTROL/policy.md
mkdir -p hive-template/CONTROL/migrations hive-template/CONTROL/skills
touch hive-template/CONTROL/migrations/.gitkeep hive-template/CONTROL/skills/.gitkeep
```

- [ ] **Step 2: Update `hive-template/.gitignore`**

Append so it reads:
```
# Private, per-client content: NEVER synced to the live hive.
/private/
.claude/skills-local/
# Client-local control-plane state: NEVER synced.
/.applied.json
/.control-block
```

- [ ] **Step 3: Wire the hook** — replace the import + `main` in `client-kit/.claude/hooks/sync_pull.py`

```python
sys.path.insert(0, str(_repo_root(__file__)))
from lib.gitsync import pull
from lib.control_plane import apply_control_plane
from lib.meeting_rollup import roll_up_all

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    print(pull(a.repo))
    cp = apply_control_plane(a.repo)
    if cp["blocked"]:
        print("=== CONTROL PLANE: BLOCKED ===")
        for r in cp["gate_reasons"]:
            print(f"  - {r}")
        print("Update your client (re-run setup_client with the latest harness), then restart.")
        if cp["policy_text"]:
            print(cp["policy_text"])
        return  # apply nothing else, skip roll-up
    if cp["migrations_applied"]:
        print(f"control: applied migrations {cp['migrations_applied']}")
    if cp["skills_changed"]:
        print(f"control: skills {cp['skills_changed']}")
    for m in cp["mcp_announcements"]:
        print(f"control: NEW MCP required: {m['name']} -> {m['how']}")
    if cp["policy_text"]:
        print(cp["policy_text"])
    for name, status in roll_up_all(a.repo):
        print(f"rollup {name}: {status}")
```

- [ ] **Step 4: Update `tools/setup_client.py`** — after vendoring lib and before returning, seed skills + `.applied.json` and extend the exclude. Replace the exclude line and add seeding:

```python
    shutil.copytree(LIB, dest / "lib", dirs_exist_ok=True)
    # Materialize the shared skills mirror and seed control-plane bookkeeping so a
    # fresh client starts current (the clone already carries the post-migration tree).
    sys.path.insert(0, str(dest)) if str(dest) not in sys.path else None
    from lib.control_plane import sync_skills, read_manifest, write_applied, _migration_id
    sync_skills(dest)
    manifest = read_manifest(dest)
    migs = sorted((dest / "CONTROL" / "migrations").glob("*.json")) \
        if (dest / "CONTROL" / "migrations").is_dir() else []
    mig_ids = [i for i in (_migration_id(p) for p in migs) if i is not None]
    structure_version = max(mig_ids, default=0)
    write_applied(dest, {
        "skills_version": manifest.get("skills_version", 0),
        "structure_version": structure_version,
        "policy_version": manifest.get("policy_version", 0),
        "announced_mcps": [m["name"] for m in manifest.get("required_mcps", [])],
    })
    for d in PRIVATE_DIRS:
        (dest / "private" / d).mkdir(parents=True, exist_ok=True)
    (dest / "private" / "TODO.md").write_text("# TODO\n")
    exclude = dest / ".git" / "info" / "exclude"
    exclude.write_text("/private/\n/lib/\n/.claude/\n/publish_allowlist.txt\n"
                       "/.applied.json\n/.control-block\n")
    return dest
```
(Keep the existing clone/config/`.claude`/allowlist lines above unchanged.)

> **Note:** the seed derives `structure_version` from the migration filenames, NOT from `manifest.structure_version`. The manifest's `structure_version` field is not read by any code path (`pending_migrations` compares only against `.applied.json`); it is informational. Do not "fix" the seed to read it.

- [ ] **Step 5: Write an integration test for provisioning**

```python
# add to tests/test_control_plane_integration.py
from tools.instantiate import instantiate
from tools.setup_client import setup_client
from lib.control_plane import read_applied

def _bare_from(local, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def test_setup_client_seeds_applied_and_mirrors_skills(tmp_path):
    hive = instantiate(tmp_path / "hive")
    remote = _bare_from(hive, tmp_path)
    client = setup_client(str(remote), tmp_path / "client")
    # process-meeting skill was vendored into CONTROL/skills and mirrored to .claude/skills
    assert (client / ".claude" / "skills" / "process-meeting" / "SKILL.md").exists()
    ap = read_applied(client)
    assert "skills_version" in ap and "announced_mcps" in ap
    # a fresh session-start applies nothing new (already current)
```

- [ ] **Step 6: Run the whole suite** (`./.venv/bin/python -m pytest -q`) — all green.
- [ ] **Step 7: Commit** (`feat: wire control plane into hook; seed client; relocate process-meeting to CONTROL/skills`).

---

## Task 9: `tools/purge.py`

**Files:** Create `tools/purge.py`; Test `tests/test_purge.py`.

**Context:** scrub a path from all history. Dry-run by default; `--force` executes filter-branch over all refs, drops `refs/original`, expires reflog, gc-prunes, prints the runbook.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_purge.py
import subprocess
from pathlib import Path
from lib.gitsync import run_git
from tests.conftest import init_identity
from tools.purge import purge

def test_purge_removes_path_from_all_history(tmp_path):
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True)
    init_identity(repo)
    (repo / "secret.txt").write_text("leaked token\n")
    (repo / "keep.txt").write_text("fine\n")
    run_git(repo, "add", "-A"); run_git(repo, "commit", "-m", "with secret")
    (repo / "later.txt").write_text("more\n")
    run_git(repo, "add", "-A"); run_git(repo, "commit", "-m", "later")

    purge(repo, "secret.txt", force=True)

    # object no longer reachable from any ref
    objs = run_git(repo, "rev-list", "--all", "--objects").stdout
    assert "secret.txt" not in objs
    assert (repo / "keep.txt").exists()

def test_purge_dry_run_does_not_change_history(tmp_path):
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True)
    init_identity(repo)
    (repo / "secret.txt").write_text("leaked\n")
    run_git(repo, "add", "-A"); run_git(repo, "commit", "-m", "x")
    before = run_git(repo, "rev-parse", "HEAD").stdout
    purge(repo, "secret.txt", force=False)  # dry run
    after = run_git(repo, "rev-parse", "HEAD").stdout
    assert before == after
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
# tools/purge.py
"""Admin tool: scrub a path from all git history (leaked private data).
Rare and destructive. Dry-run by default; pass --force to execute."""
import subprocess
import sys
from pathlib import Path

RUNBOOK = """
PURGE COMPLETE. Mandatory follow-up:
  1. Force-push the rewritten history:  git push --force --all && git push --force --tags
  2. Tell every member to re-clone (their old clones still contain the data).
  3. Rotate any exposed secret (assume it leaked).
Coordinate: announce the purge and confirm no one is mid-push before force-pushing.
"""

def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=check)

def purge(repo, path, force=False):
    repo = Path(repo)
    if not force:
        print(f"[dry-run] would remove '{path}' from ALL history of {repo}")
        print("[dry-run] re-run with --force to execute.")
        print(RUNBOOK)
        return
    env_cmd = f"git rm -r --cached --ignore-unmatch {path}"
    _git(repo, "filter-branch", "--force", "--index-filter", env_cmd,
         "--prune-empty", "--tag-name-filter", "cat", "--", "--all")
    # drop the filter-branch backups, then expire + gc so the blob is unrecoverable
    refs = _git(repo, "for-each-ref", "--format=%(refname)", "refs/original/", check=False).stdout.split()
    for ref in refs:
        _git(repo, "update-ref", "-d", ref, check=False)
    _git(repo, "reflog", "expire", "--expire=now", "--all", check=False)
    _git(repo, "gc", "--prune=now", "--aggressive", check=False)
    print(RUNBOOK)

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    if len(args) != 1:
        print("usage: python3 tools/purge.py <path> [--force]", file=sys.stderr)
        raise SystemExit(2)
    purge(Path.cwd(), args[0], force="--force" in sys.argv)
```

- [ ] **Step 4: Run to verify it passes** (2 passed).
- [ ] **Step 5: Commit** (`feat: admin purge tool (scrub leaked path from all history)`).

---

## Task 10: End-to-end + docs

**Files:** Create `tests/test_control_plane_e2e.py`; Modify `README.md`, `docs/getting-started.md`.

- [ ] **Step 1: Write the e2e test**

```python
# tests/test_control_plane_e2e.py
import json, subprocess, sys
from pathlib import Path
from tools.instantiate import instantiate
from tools.setup_client import setup_client
from lib.gitsync import run_git

def _bare_from(local, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def test_admin_change_converges_on_client(tmp_path):
    hive = instantiate(tmp_path / "hive")
    remote = _bare_from(hive, tmp_path)
    client = setup_client(str(remote), tmp_path / "client")

    # admin (edit the hive clone) bumps manifest: new skill + migration + MCP + policy
    man = json.loads((hive / "CONTROL" / "manifest.json").read_text())
    man["skills_version"] += 1
    man["structure_version"] = 1
    man["policy_version"] += 1
    man["required_mcps"] = [{"name": "granola", "how": "authorize in settings"}]
    (hive / "CONTROL" / "manifest.json").write_text(json.dumps(man))
    sk = hive / "CONTROL" / "skills" / "newskill"; sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("new")
    (hive / "CONTROL" / "migrations").mkdir(exist_ok=True)
    (hive / "CONTROL" / "migrations" / "0001-add-legal.json").write_text(json.dumps(
        {"ops": [{"op": "keep_file", "path": "engineering/legal/.gitkeep"}]}))
    (hive / "CONTROL" / "policy.md").write_text("new standing rules\n")
    run_git(hive, "add", "-A"); run_git(hive, "commit", "-m", "admin: bump control plane")
    run_git(hive, "push", "origin", "main")

    # client session start
    r = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (client / ".claude" / "skills" / "newskill" / "SKILL.md").exists()
    assert (client / "engineering" / "legal" / ".gitkeep").exists()
    assert "NEW MCP required: granola" in r.stdout
    assert "new standing rules" in r.stdout

    # migration reached the remote
    verify = tmp_path / "verify"
    subprocess.run(["git", "clone", str(remote), str(verify)], check=True)
    assert (verify / "engineering" / "legal" / ".gitkeep").exists()

    # second run is a clean no-op (no new announcements)
    r2 = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client)], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert "NEW MCP required" not in r2.stdout
```

- [ ] **Step 2: Run to verify it passes** (iterate until green), then run the whole suite.

- [ ] **Step 3: Docs**
- `README.md`: bump status badge to `3/5 sub-projects`; bump the tests badge to the new count (also fold in the pending `37 -> N` correction); update the Status section to list sub-projects 1-3 done and 4-5 remaining; add a short "Control plane" bullet under How it works (admin edits CONTROL/, clients converge on session start; gated safe-halt).
- `docs/getting-started.md`: add an "Admin: evolve the hive" subsection (edit `CONTROL/manifest.json` + add a `CONTROL/migrations/NNNN-slug.json` / drop a skill in `CONTROL/skills/` / add a `required_mcps` entry / edit `policy.md`, then push; clients converge next session), and a "Purge leaked data" note pointing at `tools/purge.py`. Add command-reference rows for both.

- [ ] **Step 4: Commit** (`test: control-plane e2e; docs: mark sub-project 3 shipped`).

---

## Final: after all tasks

- [ ] Run the full suite once more: `./.venv/bin/python -m pytest -q` (all green).
- [ ] Use **superpowers:finishing-a-development-branch**. Given `main` is branch-protected, the expected path is **Option 1 (push and open a PR)** for your own review/merge.
