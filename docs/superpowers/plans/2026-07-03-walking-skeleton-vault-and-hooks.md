# Walking Skeleton: Vault + Two Sync Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the open-source monorepo skeleton and prove the core loop: instantiate a live hive, set up a client clone, and let a person explicitly publish shared content upstream and pull others' changes down, with private content never leaving the machine and concurrent pushes never overwriting each other.

**Architecture:** A single open-source monorepo (`ai-team-brain`) holds `hive-template/`, `client-kit/`, `lib/`, `tools/`, `tests/`, and `docs/`. A live hive is a separate Git repo instantiated from `hive-template/`. A client is a clone of a live hive with a gitignored `private/` tree and two Python hooks (`sync_pull.py`, `publish.py`) that wrap git. All git logic lives in `lib/gitsync.py` and is unit-tested against temporary bare remotes.

**Tech Stack:** Python 3.11+, `git` CLI (via `subprocess`), `pytest`. Hooks are Python for portability and testability (consistent with the existing `memory-health.py` precedent). Shell is only used to invoke Python.

**Scope note:** This is sub-project 1 of 5 from the design spec (`docs/superpowers/specs/2026-07-03-group-hive-brain-design.md`). It deliberately excludes the control plane, meeting roll-up, TTL port, and the full SSH/role installer. It includes a *minimal* client setup helper only so the loop is end-to-end testable.

**Build location:** Create the monorepo at `~/ai-team-brain`. All paths below are relative to that root unless absolute.

---

## File Structure

- `pyproject.toml` — pytest config + package metadata.
- `.gitignore` — the monorepo's own ignores (`__pycache__`, `.pytest_cache`, test scratch).
- `README.md` — getting-started walkthrough (Task 11).
- `lib/gitsync.py` — all git helpers: `run_git`, `pull`, `stage_allowlist`, `publish` (rebase/retry). Single responsibility: git operations. Unit-tested.
- `hive-template/` — empty live-hive scaffolding: `CONTROL/manifest.json`, functional dirs, and the live-hive `.gitignore` that ignores `private/` and `.claude/skills-local/`.
- `client-kit/CLAUDE.md` — group operating model (seed; can start minimal).
- `client-kit/.claude/hooks/sync_pull.py` — session-start entrypoint calling `lib.gitsync.pull`.
- `client-kit/.claude/hooks/publish.py` — publish entrypoint calling `lib.gitsync.publish`.
- `client-kit/.claude/settings.local.json` — wires the SessionStart hook.
- `client-kit/publish_allowlist.txt` — newline-separated shared pathspecs allowed to publish.
- `tools/instantiate.py` — create a live hive from `hive-template/` + `client-kit/skills`.
- `tools/setup_client.py` — minimal: clone a live hive, create `private/` tree, install hooks.
- `tests/conftest.py` — fixtures: git identity, bare remote, helper to make commits.
- `tests/test_*.py` — one file per unit + one end-to-end test.

---

## Task 1: Monorepo scaffolding

**Files:**
- Create: `~/ai-team-brain/.gitignore`, `~/ai-team-brain/pyproject.toml`, `~/ai-team-brain/lib/__init__.py`, `~/ai-team-brain/tests/__init__.py`

- [ ] **Step 1: Create the repo and directory skeleton**

```bash
mkdir -p ~/ai-team-brain/{lib,tools,tests,client-kit/.claude/hooks,hive-template/CONTROL,docs}
cd ~/ai-team-brain && git init && git branch -M main
```

- [ ] **Step 2: Write `.gitignore` and `pyproject.toml`**

`.gitignore`:
```
__pycache__/
*.pyc
.pytest_cache/
.scratch/
```

`pyproject.toml`:
```toml
[project]
name = "ai-team-brain"
version = "0.0.1"
requires-python = ">=3.11"

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 3: Create empty package markers**

Create empty `lib/__init__.py` and `tests/__init__.py`.

- [ ] **Step 4: Verify pytest runs (no tests yet)**

Run: `cd ~/ai-team-brain && python3 -m pytest -q`
Expected: `no tests ran` (exit code 5), not an import/config error.

- [ ] **Step 5: Commit**

```bash
cd ~/ai-team-brain && git add -A && git commit -m "chore: monorepo scaffolding"
```

---

## Task 2: `run_git` helper

**Files:**
- Create: `lib/gitsync.py`
- Test: `tests/conftest.py`, `tests/test_run_git.py`

- [ ] **Step 1: Write conftest fixtures**

`tests/conftest.py`:
```python
import subprocess
import pytest

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)

def init_identity(repo):
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

@pytest.fixture
def bare_remote(tmp_path):
    """A bare repo standing in for GitHub, plus a seeded main branch."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    # seed with an initial commit via a scratch clone
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", str(remote), str(seed)], check=True)
    init_identity(seed)
    (seed / "README.md").write_text("seed\n")
    _git(seed, "add", "-A"); _git(seed, "commit", "-m", "init")
    _git(seed, "push", "origin", "main")
    return remote
```

- [ ] **Step 2: Write the failing test**

`tests/test_run_git.py`:
```python
from lib.gitsync import run_git

def test_run_git_returns_output(bare_remote, tmp_path):
    clone = tmp_path / "c"
    import subprocess
    subprocess.run(["git", "clone", str(bare_remote), str(clone)], check=True)
    result = run_git(clone, "rev-parse", "--abbrev-ref", "HEAD")
    assert result.stdout.strip() == "main"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_run_git.py -q`
Expected: FAIL, `ImportError: cannot import name 'run_git'`.

- [ ] **Step 4: Implement `run_git`**

`lib/gitsync.py`:
```python
import subprocess

def run_git(repo, *args, check=True):
    """Run `git -C <repo> <args>`; return the CompletedProcess."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_run_git.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add lib/gitsync.py tests/conftest.py tests/test_run_git.py && git commit -m "feat: run_git helper + test harness"
```

---

## Task 3: hive-template structure + live-hive .gitignore

**Files:**
- Create: `hive-template/CONTROL/manifest.json`, `hive-template/.gitignore`, `hive-template/README.md`, and `.gitkeep` in each functional dir.
- Test: `tests/test_template_gitignore.py`

- [ ] **Step 1: Write the failing test**

`tests/test_template_gitignore.py`:
```python
from pathlib import Path

TEMPLATE = Path.home() / "ai-team-brain" / "hive-template"

def test_functional_dirs_exist():
    for d in ["org", "product", "engineering", "design", "customers",
              "market", "knowledge", "projects", "decisions", "meetings", "CONTROL"]:
        assert (TEMPLATE / d).is_dir(), f"missing {d}"

def test_gitignore_blocks_private_and_local_skills():
    text = (TEMPLATE / ".gitignore").read_text()
    assert "/private/" in text
    assert ".claude/skills-local/" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_template_gitignore.py -q`
Expected: FAIL (dirs / file missing).

- [ ] **Step 3: Create the template**

```bash
cd ~/ai-team-brain/hive-template
mkdir -p org product engineering design customers market knowledge projects decisions meetings CONTROL
for d in org product engineering design customers market knowledge projects decisions meetings; do touch "$d/.gitkeep"; done
```

`hive-template/.gitignore`:
```
# Private, per-client content: NEVER synced to the live hive.
/private/
.claude/skills-local/
```

`hive-template/CONTROL/manifest.json`:
```json
{
  "skills_version": 1,
  "structure_version": 1,
  "min_client_version": "0.0.1",
  "required_mcps": [],
  "policy_version": 1
}
```

`hive-template/README.md`: one line describing that this is the empty vault scaffolding.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_template_gitignore.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hive-template && git commit -m "feat: hive-template scaffolding + live-hive gitignore"
```

---

## Task 4: `instantiate.py` (live hive from template)

**Files:**
- Create: `tools/instantiate.py`, `client-kit/skills/.gitkeep`
- Test: `tests/test_instantiate.py`

- [ ] **Step 1: Write the failing test**

`tests/test_instantiate.py`:
```python
import subprocess
from pathlib import Path
from tools.instantiate import instantiate

def test_instantiate_creates_committed_hive(tmp_path):
    dest = tmp_path / "acme-hive"
    instantiate(dest)
    assert (dest / "CONTROL" / "manifest.json").is_file()
    assert (dest / "engineering").is_dir()
    # it is a git repo with one commit
    log = subprocess.run(["git", "-C", str(dest), "log", "--oneline"],
                         capture_output=True, text=True, check=True)
    assert len(log.stdout.strip().splitlines()) == 1
    # CONTROL/skills vendored from client-kit
    assert (dest / "CONTROL" / "skills").is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_instantiate.py -q`
Expected: FAIL, import error.

- [ ] **Step 3: Implement `instantiate` and add `client-kit/skills/.gitkeep`**

`tools/instantiate.py`:
```python
import shutil
from pathlib import Path
from lib.gitsync import run_git

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "hive-template"
CLIENT_SKILLS = ROOT / "client-kit" / "skills"

def instantiate(dest):
    """Create a new live-hive git repo from hive-template, vendoring CONTROL skills."""
    dest = Path(dest)
    shutil.copytree(TEMPLATE, dest)
    # vendor canonical skills into CONTROL/skills
    (dest / "CONTROL" / "skills").mkdir(parents=True, exist_ok=True)
    if CLIENT_SKILLS.exists():
        shutil.copytree(CLIENT_SKILLS, dest / "CONTROL" / "skills", dirs_exist_ok=True)
    run_git(dest, "init", "-b", "main")
    run_git(dest, "config", "user.email", "hive@example.com")
    run_git(dest, "config", "user.name", "Hive Bootstrap")
    run_git(dest, "add", "-A")
    run_git(dest, "commit", "-m", "chore: instantiate live hive from template")
    return dest
```

Create empty `client-kit/skills/.gitkeep`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_instantiate.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tools/instantiate.py client-kit/skills/.gitkeep tests/test_instantiate.py && git commit -m "feat: instantiate live hive from template"
```

---

## Task 5: `stage_allowlist` (explicit publish safety)

**Files:**
- Modify: `lib/gitsync.py`
- Create: `client-kit/publish_allowlist.txt`
- Test: `tests/test_stage_allowlist.py`

- [ ] **Step 1: Write the failing test**

`tests/test_stage_allowlist.py`:
```python
import subprocess
from pathlib import Path
from lib.gitsync import stage_allowlist, run_git

def _clone(bare, dest):
    subprocess.run(["git", "clone", str(bare), str(dest)], check=True)
    run_git(dest, "config", "user.email", "a@b.c")
    run_git(dest, "config", "user.name", "A")

def test_only_allowlisted_paths_are_staged(bare_remote, tmp_path):
    clone = tmp_path / "c"; _clone(bare_remote, clone)
    (clone / "engineering").mkdir()
    (clone / "engineering" / "note.md").write_text("shared\n")
    (clone / "private").mkdir()
    (clone / "private" / "secret.md").write_text("PRIVATE\n")
    # gitignore private so it cannot be added
    (clone / ".gitignore").write_text("/private/\n")
    run_git(clone, "add", ".gitignore"); run_git(clone, "commit", "-m", "ignore")

    stage_allowlist(clone, ["engineering/"])
    staged = run_git(clone, "diff", "--cached", "--name-only").stdout.split()
    assert "engineering/note.md" in staged
    assert not any("private" in s for s in staged)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_stage_allowlist.py -q`
Expected: FAIL, import error.

- [ ] **Step 3: Implement `stage_allowlist` + write the allowlist file**

Append to `lib/gitsync.py`:
```python
def stage_allowlist(repo, allow_paths):
    """Stage only the given pathspecs. Private paths are gitignored, so even a
    stray pathspec cannot stage them; the allowlist is the primary guard and
    gitignore is the backstop."""
    for p in allow_paths:
        # check=False so a missing/empty pathspec does not abort the whole publish
        run_git(repo, "add", "--", p, check=False)

def read_allowlist(path):
    lines = []
    for raw in open(path):
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines
```

`client-kit/publish_allowlist.txt`:
```
# Shared pathspecs that may be published upstream. Everything else stays local.
org/
product/
engineering/
design/
customers/
market/
knowledge/
projects/
decisions/
meetings/
CONTROL/
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_stage_allowlist.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/gitsync.py client-kit/publish_allowlist.txt tests/test_stage_allowlist.py && git commit -m "feat: allowlist staging for explicit publish"
```

---

## Task 6: `publish` with rebase/retry (no overwrite under concurrency)

**Files:**
- Modify: `lib/gitsync.py`
- Test: `tests/test_publish_concurrent.py`

- [ ] **Step 1: Write the failing test (simulates a second writer racing in)**

`tests/test_publish_concurrent.py`:
```python
import subprocess
from pathlib import Path
from lib.gitsync import publish, run_git

def _clone(bare, dest, email):
    subprocess.run(["git", "clone", str(bare), str(dest)], check=True)
    run_git(dest, "config", "user.email", email)
    run_git(dest, "config", "user.name", email)

def test_concurrent_publish_no_overwrite(bare_remote, tmp_path):
    a = tmp_path / "a"; _clone(bare_remote, a, "alice@x")
    b = tmp_path / "b"; _clone(bare_remote, b, "bob@x")

    # Bob pushes first, out of band
    (b / "engineering").mkdir(); (b / "engineering" / "bob.md").write_text("bob\n")
    run_git(b, "add", "-A"); run_git(b, "commit", "-m", "bob"); run_git(b, "push", "origin", "main")

    # Alice publishes her own (disjoint) file; her first push will be rejected,
    # then rebase+retry must succeed and preserve Bob's file.
    (a / "engineering").mkdir(exist_ok=True); (a / "engineering" / "alice.md").write_text("alice\n")
    result = publish(a, "alice", ["engineering/"])
    assert result == "pushed"

    # Verify both files exist on the remote (via a fresh clone)
    c = tmp_path / "c"
    subprocess.run(["git", "clone", str(bare_remote), str(c)], check=True)
    assert (c / "engineering" / "bob.md").exists()
    assert (c / "engineering" / "alice.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_publish_concurrent.py -q`
Expected: FAIL, import error.

- [ ] **Step 3: Implement `publish`**

Append to `lib/gitsync.py`:
```python
def publish(repo, message, allow_paths, remote="origin", branch="main", max_retries=5):
    """Stage allowlisted paths, commit if there is anything, then push with
    fetch->rebase->retry so a concurrent push is caught up to, never clobbered."""
    stage_allowlist(repo, allow_paths)
    staged = run_git(repo, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return "nothing-to-publish"
    run_git(repo, "commit", "-m", message)
    for _ in range(max_retries):
        push = run_git(repo, "push", remote, branch, check=False)
        if push.returncode == 0:
            return "pushed"
        # rejected (likely non-fast-forward): catch up and retry
        run_git(repo, "fetch", remote, branch)
        rebase = run_git(repo, "rebase", f"{remote}/{branch}", check=False)
        if rebase.returncode != 0:
            run_git(repo, "rebase", "--abort", check=False)
            raise RuntimeError("publish: rebase conflict on a shared file; needs manual resolution")
    raise RuntimeError("publish: push failed after retries")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_publish_concurrent.py -q`
Expected: PASS (both files present on remote).

- [ ] **Step 5: Commit**

```bash
git add lib/gitsync.py tests/test_publish_concurrent.py && git commit -m "feat: publish with rebase/retry (concurrency-safe)"
```

---

## Task 7: `pull` (downstream)

**Files:**
- Modify: `lib/gitsync.py`
- Test: `tests/test_pull.py`

- [ ] **Step 1: Write the failing test**

`tests/test_pull.py`:
```python
import subprocess
from pathlib import Path
from lib.gitsync import pull, run_git

def _clone(bare, dest, email):
    subprocess.run(["git", "clone", str(bare), str(dest)], check=True)
    run_git(dest, "config", "user.email", email); run_git(dest, "config", "user.name", email)

def test_pull_sees_others_changes(bare_remote, tmp_path):
    a = tmp_path / "a"; _clone(bare_remote, a, "a@x")
    b = tmp_path / "b"; _clone(bare_remote, b, "b@x")
    (a / "product").mkdir(); (a / "product" / "roadmap.md").write_text("v1\n")
    run_git(a, "add", "-A"); run_git(a, "commit", "-m", "roadmap"); run_git(a, "push", "origin", "main")
    pull(b)
    assert (b / "product" / "roadmap.md").read_text() == "v1\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_pull.py -q`
Expected: FAIL, import error.

- [ ] **Step 3: Implement `pull`**

Append to `lib/gitsync.py`:
```python
def pull(repo, remote="origin", branch="main"):
    """Session-start pull. Rebase local (unpushed) work on top of remote.
    Private/ is gitignored, so nothing local-only is touched."""
    run_git(repo, "fetch", remote, branch)
    run_git(repo, "rebase", f"{remote}/{branch}")
    return "pulled"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_pull.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/gitsync.py tests/test_pull.py && git commit -m "feat: session-start pull"
```

---

## Task 8: Hook entrypoints + client kit wiring

**Files:**
- Create: `client-kit/.claude/hooks/sync_pull.py`, `client-kit/.claude/hooks/publish.py`, `client-kit/.claude/settings.local.json`, `client-kit/CLAUDE.md`
- Test: `tests/test_hook_entrypoints.py`

- [ ] **Step 1: Write the failing test**

`tests/test_hook_entrypoints.py`:
```python
import subprocess, sys
from pathlib import Path
from lib.gitsync import run_git

ROOT = Path(__file__).resolve().parents[1]  # repo root, relative to tests/
PUBLISH_HOOK = ROOT / "client-kit" / ".claude" / "hooks" / "publish.py"

def _clone(bare, dest, email):
    subprocess.run(["git", "clone", str(bare), str(dest)], check=True)
    run_git(dest, "config", "user.email", email); run_git(dest, "config", "user.name", email)

def test_publish_hook_publishes(bare_remote, tmp_path):
    a = tmp_path / "a"; _clone(bare_remote, a, "a@x")
    (a / "engineering").mkdir(); (a / "engineering" / "n.md").write_text("x\n")
    # allowlist file lives in the client kit; pass it explicitly
    allow = ROOT / "client-kit" / "publish_allowlist.txt"
    r = subprocess.run([sys.executable, str(PUBLISH_HOOK),
                        "--repo", str(a), "--allowlist", str(allow), "--message", "hook"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    c = tmp_path / "c"; subprocess.run(["git", "clone", str(bare_remote), str(c)], check=True)
    assert (c / "engineering" / "n.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_hook_entrypoints.py -q`
Expected: FAIL (hook file missing).

- [ ] **Step 3: Implement the hooks and wiring**

`client-kit/.claude/hooks/publish.py`:
```python
#!/usr/bin/env python3
import argparse, sys
from pathlib import Path

def _repo_root(start):
    """Walk up from this file until we find the dir containing lib/gitsync.py.
    Works in both layouts, which put lib/ at different depths: the monorepo
    (client-kit/.claude/hooks/...) and a client clone (<clone>/.claude/hooks/...)."""
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / "lib" / "gitsync.py").exists():
            return cand
    raise RuntimeError("could not locate lib/gitsync.py above " + str(p))

sys.path.insert(0, str(_repo_root(__file__)))
from lib.gitsync import publish, read_allowlist

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--allowlist", required=True)
    ap.add_argument("--message", default="publish")
    a = ap.parse_args()
    result = publish(a.repo, a.message, read_allowlist(a.allowlist))
    print(result)

if __name__ == "__main__":
    main()
```

`client-kit/.claude/hooks/sync_pull.py`:
```python
#!/usr/bin/env python3
import argparse, sys
from pathlib import Path

def _repo_root(start):
    """Walk up from this file until we find the dir containing lib/gitsync.py
    (same helper as publish.py; works in both the monorepo and a client clone)."""
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / "lib" / "gitsync.py").exists():
            return cand
    raise RuntimeError("could not locate lib/gitsync.py above " + str(p))

sys.path.insert(0, str(_repo_root(__file__)))
from lib.gitsync import pull

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    print(pull(a.repo))

if __name__ == "__main__":
    main()
```

`client-kit/.claude/settings.local.json` (SessionStart wiring; `$CLAUDE_PROJECT_DIR` is the client clone):
```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [ { "type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR/.claude/hooks/sync_pull.py\" --repo \"$CLAUDE_PROJECT_DIR\"" } ] }
    ]
  }
}
```

`client-kit/CLAUDE.md`: a minimal seed stating this is a group hive-brain client (can be expanded later; keep to a few lines now).

Note on the import path: the hooks locate `lib/` by walking up to the directory that contains `lib/gitsync.py`, so the same code works whether the hook runs from the monorepo (`client-kit/.claude/hooks/...`, with `lib/` at the monorepo root) or from a client clone (`<clone>/.claude/hooks/...`, with `lib/` vendored at the clone root by Task 9). This is why a hardcoded parent depth is avoided: the two layouts put `lib/` at different depths. Task 8's test runs the hook from the monorepo copy; Task 10's e2e runs it from a client clone, so both layouts are exercised.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_hook_entrypoints.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add client-kit tests/test_hook_entrypoints.py && git commit -m "feat: sync_pull + publish hook entrypoints and client wiring"
```

---

## Task 9: `setup_client.py` (minimal client provisioning)

**Files:**
- Create: `tools/setup_client.py`
- Test: `tests/test_setup_client.py`

- [ ] **Step 1: Write the failing test**

`tests/test_setup_client.py`:
```python
from pathlib import Path
from tools.setup_client import setup_client

def test_setup_client_creates_private_tree_and_hooks(bare_remote, tmp_path):
    clone = tmp_path / "me"
    setup_client(str(bare_remote), clone)
    # private tree exists and is gitignored
    for d in ["personal-meetings", "personal-context", "personal-decisions",
              "personal-docs", "personal-drafts", "personal-projects", "personal-reviews"]:
        assert (clone / "private" / d).is_dir()
    assert (clone / "private" / "TODO.md").is_file()
    # hooks + lib vendored in
    assert (clone / ".claude" / "hooks" / "publish.py").is_file()
    assert (clone / "lib" / "gitsync.py").is_file()
    # private is ignored by git
    import subprocess
    out = subprocess.run(["git", "-C", str(clone), "status", "--porcelain"],
                         capture_output=True, text=True, check=True).stdout
    assert "private/" not in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_setup_client.py -q`
Expected: FAIL, import error.

- [ ] **Step 3: Implement `setup_client`**

`tools/setup_client.py`:
```python
import shutil, subprocess
from pathlib import Path
from lib.gitsync import run_git

ROOT = Path(__file__).resolve().parents[1]
CLIENT_KIT = ROOT / "client-kit"
LIB = ROOT / "lib"

PRIVATE_DIRS = ["personal-meetings", "personal-context", "personal-decisions",
                "personal-docs", "personal-drafts", "personal-projects", "personal-reviews"]

def setup_client(remote_url, dest):
    """Clone the live hive, vendor hooks + lib, and build the gitignored private tree.
    Minimal stand-in for the full installer (sub-project 5); no SSH/role handling."""
    dest = Path(dest)
    subprocess.run(["git", "clone", str(remote_url), str(dest)], check=True)
    run_git(dest, "config", "user.email", "member@example.com")
    run_git(dest, "config", "user.name", "Member")
    # vendor the client kit's .claude and the lib
    shutil.copytree(CLIENT_KIT / ".claude", dest / ".claude", dirs_exist_ok=True)
    shutil.copy2(CLIENT_KIT / "publish_allowlist.txt", dest / "publish_allowlist.txt")
    shutil.copytree(LIB, dest / "lib", dirs_exist_ok=True)
    # private tree (gitignored by the hive's .gitignore, which came from the template)
    for d in PRIVATE_DIRS:
        (dest / "private" / d).mkdir(parents=True, exist_ok=True)
    (dest / "private" / "TODO.md").write_text("# TODO\n")
    # Keep vendored, intentionally-untracked tooling out of `git status` via a
    # LOCAL ignore (.git/info/exclude), which never touches the shared repo's
    # committed .gitignore. /private/ is ALSO ignored by the live hive's committed
    # .gitignore in production; listing it here is defense-in-depth and makes the
    # private tree ignored even when the client is cloned from a plain remote.
    exclude = dest / ".git" / "info" / "exclude"
    exclude.write_text("/private/\n/lib/\n/.claude/\n/publish_allowlist.txt\n")
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_setup_client.py -q`
Expected: PASS. `private/` is kept out of `git status` by the `/private/` entry written to `.git/info/exclude` (so the test does not depend on the remote carrying the hive `.gitignore`).

- [ ] **Step 5: Commit**

```bash
git add tools/setup_client.py tests/test_setup_client.py && git commit -m "feat: minimal client setup (clone, vendor, private tree)"
```

---

## Task 10: End-to-end walking-skeleton test

**Files:**
- Test: `tests/test_e2e_loop.py`

- [ ] **Step 1: Write the end-to-end test**

`tests/test_e2e_loop.py`:
```python
import subprocess, sys
from pathlib import Path
from tools.instantiate import instantiate
from tools.setup_client import setup_client
from lib.gitsync import run_git, pull

ROOT = Path(__file__).resolve().parents[1]  # repo root, relative to tests/

def _bare_from(local, tmp_path):
    """Publish a local repo to a fresh bare remote and return the remote path."""
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def test_full_loop(tmp_path):
    # 1. instantiate a live hive and publish it to a bare "GitHub"
    hive = instantiate(tmp_path / "acme-hive")
    remote = _bare_from(hive, tmp_path)

    # 2. two members set up clients
    alice = setup_client(str(remote), tmp_path / "alice")
    bob = setup_client(str(remote), tmp_path / "bob")

    # 3. Alice writes a private note (must never sync) and a shared note (must sync)
    (alice / "private" / "personal-context" / "me.md").write_text("my growth goals\n")
    (alice / "engineering" / "adr-001.md").write_text("decision\n")

    # 4. Alice publishes via the hook
    r = subprocess.run([sys.executable, str(alice / ".claude" / "hooks" / "publish.py"),
                        "--repo", str(alice), "--allowlist", str(alice / "publish_allowlist.txt"),
                        "--message", "adr"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "pushed", r.stdout  # not "nothing-to-publish"

    # 5. Bob pulls and sees the shared note but NOT Alice's private note
    pull(bob)
    assert (bob / "engineering" / "adr-001.md").exists()
    assert not (bob / "private" / "personal-context" / "me.md").exists()

    # 6. The private note never reached the remote
    checkout = tmp_path / "verify"
    subprocess.run(["git", "clone", str(remote), str(checkout)], check=True)
    assert not (checkout / "private").exists()
```

- [ ] **Step 2: Run the full suite**

Run: `cd ~/ai-team-brain && python3 -m pytest -q`
Expected: ALL PASS, including the e2e loop.

- [ ] **Step 3: Commit**

```bash
git add tests/test_e2e_loop.py && git commit -m "test: end-to-end walking-skeleton loop"
```

---

## Task 11: Getting-started docs

**Files:**
- Create: `docs/getting-started.md`
- Modify: `README.md`

- [ ] **Step 1: Write `docs/getting-started.md`**

Cover, as a walkthrough: (a) what the monorepo is, (b) `python3 tools/instantiate.py <dest>` to create a live hive and push it to a new private GitHub repo, (c) `python3 tools/setup_client.py <remote-url> <dest>` to provision a member, (d) how the two hooks work (session-start pull, explicit publish), (e) the private/ tree and the golden rule that only allowlisted paths publish. Keep commands copy-pasteable.

- [ ] **Step 2: Update `README.md`**

Point to `docs/getting-started.md`, state the product-vs-live-instance model in three sentences, and link the spec.

- [ ] **Step 3: Verify the documented commands actually run**

Run the instantiate + setup_client commands from a clean temp dir exactly as written in the docs; confirm they succeed.
Expected: both commands complete and produce the described trees.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/getting-started.md && git commit -m "docs: getting-started walkthrough"
```

---

## Done criteria

- `python3 -m pytest -q` passes at `~/ai-team-brain`.
- A live hive can be instantiated, two clients provisioned, a shared note published by one and pulled by the other, and a private note provably never leaves the machine.
- Concurrent publishes rebase-and-retry without overwriting.
- Getting-started docs let a newcomer reproduce the loop.

**Next sub-projects (separate plans):** 2) meeting flow + roll-up, 3) control plane + client update, 4) TTL/freshness port, 5) full installer + onboarding. Each builds on this skeleton.
