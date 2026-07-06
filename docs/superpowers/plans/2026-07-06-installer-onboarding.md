# Full Installer + Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the member-facing installer (`tools/install.py`) with an install mode and a code-only `--update` mode, a deterministic profile seeder (`lib/profile.py`), and a thin `/onboarding` skill, completing the harness (5/5 sub-projects).

**Architecture:** Client-side, stdlib only. `install.py` wraps the existing `setup_client` provisioning: preflight (git / Python / GitHub SSH, SSH-gated by URL) -> provision with the member's real identity -> seed a minimal profile carrying a deterministic author `handle`. `--update` re-vendors only harness-owned code (`lib/`, `.claude/hooks/`, `settings.local.json`, `publish_allowlist.txt`) via mirror-with-delete, preserving all local state. A thin `/onboarding` skill enriches the profile.

**Tech Stack:** Python 3.11+ (stdlib: `argparse`, `shutil`, `subprocess`, `os`, `sys`, `pathlib`), pytest, git via `lib/gitsync.py`.

**Spec:** `docs/superpowers/specs/2026-07-06-installer-onboarding-design.md`. Read it before starting; this plan implements sections 4.1-4.6.

**Branch:** work on `sp5-installer` (already checked out). Land via PR at the end (main is branch-protected).

**Test command (from repo root):** `cd /Users/stas.wishnevetsky/team-brain-harness && ./.venv/bin/python -m pytest -q`.

---

## File Structure

**Create:**
- `lib/profile.py` — `write_profile(dest, name, role, handle)`.
- `tools/install.py` — `ssh_ok`, `preflight`, `install`, `_mirror`, `update`, and a CLI.
- `client-kit/skills/onboarding/SKILL.md` — the thin first-run interview skill.
- `tests/test_profile.py`, `tests/test_install.py`.

**Modify:**
- `tools/setup_client.py` — add `name="Member", email="member@example.com"` params (defaults preserve existing callers/tests); use them in the `git config` lines.
- `client-kit/skills/process-meeting/SKILL.md` — tighten step 4 to read the explicit `handle:` field.
- `README.md` / `docs/getting-started.md` — installer-first flow, `--update`, onboarding; mark 5/5 complete.

**Reuse:** `lib/meeting_rollup.slugify` (for the handle), `lib/gitsync.run_git`, `tools/setup_client.setup_client`.

---

## Conventions

- Tests use real git against `tmp_path`; reuse `tests/conftest.py` (`bare_remote`, `init_identity`).
- Stdlib only. Commit after each task; message ends with a blank line then:
  `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`
- No em/en dashes.

---

## Task 1: `lib/profile.py`

**Files:** Create `lib/profile.py`, `tests/test_profile.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_profile.py
from lib.profile import write_profile

def test_write_profile_seeds_name_role_handle(tmp_path):
    p = write_profile(tmp_path, "Ada Lovelace", "eng", "ada")
    assert p == tmp_path / "private" / "personal-context" / "profile.md"
    text = p.read_text()
    assert "# Ada Lovelace" in text
    assert "- handle: ada" in text
    assert "- role: eng" in text
    assert "last_verified" not in text  # never freshness-tracked

def test_write_profile_idempotent(tmp_path):
    write_profile(tmp_path, "Ada", "eng", "ada")
    before = (tmp_path / "private" / "personal-context" / "profile.md").read_text()
    write_profile(tmp_path, "Ada", "eng", "ada")
    after = (tmp_path / "private" / "personal-context" / "profile.md").read_text()
    assert before == after
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement**

```python
# lib/profile.py
"""Seed a member's minimal personal-context profile. Stdlib only.
See docs/superpowers/specs/2026-07-06-installer-onboarding-design.md."""
import os
from pathlib import Path

def write_profile(dest, name, role, handle):
    """Write <dest>/private/personal-context/profile.md atomically. Minimal seed;
    the /onboarding skill enriches the prose but leaves handle/role lines intact.
    No last_verified front-matter (so freshness never flags a member's own profile)."""
    d = Path(dest) / "private" / "personal-context"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "profile.md"
    content = (f"# {name}\n\n"
               f"- handle: {handle}\n"
               f"- role: {role}\n\n"
               "(Run /onboarding to add your primary domain, current focus, and what you work on.)\n")
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text(content)
    os.replace(tmp, p)
    return p
```

- [ ] **Step 4: Run to verify it passes** (2 passed).
- [ ] **Step 5: Commit** (`feat: write_profile seeds minimal personal-context profile`).

---

## Task 2: `setup_client` identity parametrization

**Files:** Modify `tools/setup_client.py`; Test: existing `tests/test_setup_client.py` must still pass; add one assertion.

**Context:** `setup_client` currently hardcodes `member@example.com`. Add `name`/`email` params with the current values as defaults (so every existing two-arg caller and test is unchanged), and use them in the `git config` lines.

- [ ] **Step 1: Modify the signature + config lines** in `tools/setup_client.py`

Change:
```python
def setup_client(remote_url, dest):
    ...
    run_git(dest, "config", "user.email", "member@example.com")
    run_git(dest, "config", "user.name", "Member")
```
to:
```python
def setup_client(remote_url, dest, name="Member", email="member@example.com"):
    ...
    run_git(dest, "config", "user.email", email)
    run_git(dest, "config", "user.name", name)
```
(Only the signature and those two lines change; leave the rest of the function exactly as-is.)

- [ ] **Step 2: Add a test** to `tests/test_setup_client.py` asserting the params flow through

```python
def test_setup_client_sets_provided_identity(bare_remote, tmp_path):
    from tools.setup_client import setup_client
    from lib.gitsync import run_git
    d = setup_client(str(bare_remote), tmp_path / "c", name="Ada", email="ada@x.com")
    assert run_git(d, "config", "user.email").stdout.strip() == "ada@x.com"
    assert run_git(d, "config", "user.name").stdout.strip() == "Ada"
```
(If `tests/test_setup_client.py` does not import `bare_remote`, it is a conftest fixture and available by name.)

- [ ] **Step 3: Run the full suite** — the existing setup_client tests (two-arg calls) must still pass, plus the new one. Run: `cd /Users/stas.wishnevetsky/team-brain-harness && ./.venv/bin/python -m pytest -q`.
- [ ] **Step 4: Commit** (`feat: parametrize setup_client identity (defaults unchanged)`).

---

## Task 3: `install.py` preflight (`ssh_ok` + `preflight`)

**Files:** Create `tools/install.py`, `tests/test_install.py`.

**Context:** `preflight(remote_url)` returns a list of problem strings. The SSH check runs only for a `git@github.com:` URL (so local-remote tests never touch the network), and `ssh_ok` uses `BatchMode=yes` so it can never hang.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_install.py
import tools.install as install_mod
from tools.install import preflight, _is_github_ssh

def test_is_github_ssh():
    assert _is_github_ssh("git@github.com:acme/hive.git")
    assert not _is_github_ssh("/tmp/x/origin.git")
    assert not _is_github_ssh("https://github.com/acme/hive.git")

def test_preflight_flags_missing_git(monkeypatch):
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: None)
    problems = preflight("/tmp/local/origin.git")
    assert any("git" in p for p in problems)

def test_preflight_skips_ssh_for_local_remote(monkeypatch):
    # ssh_ok must not even be called for a local remote
    called = {"n": 0}
    monkeypatch.setattr(install_mod, "ssh_ok", lambda: called.__setitem__("n", called["n"] + 1) or True)
    preflight("/tmp/local/origin.git")
    assert called["n"] == 0

def test_preflight_checks_ssh_for_github_remote(monkeypatch):
    monkeypatch.setattr(install_mod, "ssh_ok", lambda: False)
    problems = preflight("git@github.com:acme/hive.git")
    assert any("SSH" in p or "ssh" in p for p in problems)
```

- [ ] **Step 2: Run to verify it fails** (ImportError).

- [ ] **Step 3: Implement the top of `tools/install.py`**

```python
# tools/install.py
"""Member-facing installer for a team-brain-harness client. Stdlib only.
See docs/superpowers/specs/2026-07-06-installer-onboarding-design.md."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.meeting_rollup import slugify
from lib.profile import write_profile
from tools.setup_client import setup_client

LIB = ROOT / "lib"
CLIENT_KIT = ROOT / "client-kit"

def ssh_ok():
    """True if GitHub SSH authenticates. `ssh -T` exits non-zero even on success,
    so we match the banner. BatchMode + accept-new guarantee no hang."""
    r = subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
         "git@github.com"], capture_output=True, text=True)
    return "successfully authenticated" in (r.stderr or "")

def _is_github_ssh(url):
    return str(url).startswith("git@github.com:")

def preflight(remote_url):
    problems = []
    if shutil.which("git") is None:
        problems.append("git is not installed")
    if sys.version_info < (3, 11):
        problems.append("Python 3.11+ is required")
    if _is_github_ssh(remote_url) and not ssh_ok():
        problems.append(
            "GitHub SSH is not reachable. Generate a key:\n"
            "  ssh-keygen -t ed25519 -C \"your-email\"\n"
            "then paste ~/.ssh/id_ed25519.pub at https://github.com/settings/keys and re-run.")
    return problems
```

- [ ] **Step 4: Run to verify it passes** (4 passed).
- [ ] **Step 5: Commit** (`feat: install.py preflight (git/python/url-gated ssh)`).

---

## Task 4: `install()` + CLI (flags with interactive fallback)

**Files:** Modify `tools/install.py`; Test `tests/test_install.py`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_install.py
import subprocess
from pathlib import Path
from tools.install import install
from lib.gitsync import run_git

def test_install_sets_identity_profile_and_working_client(bare_remote, tmp_path):
    dest = install(str(bare_remote), tmp_path / "c",
                   name="Ada", email="ada.lovelace@x.com", role="eng")
    # real identity set
    assert run_git(dest, "config", "user.email").stdout.strip() == "ada.lovelace@x.com"
    # profile seeded with a handle derived from the email local-part
    prof = (dest / "private" / "personal-context" / "profile.md").read_text()
    assert "# Ada" in prof and "- role: eng" in prof
    assert "- handle: ada-lovelace" in prof
    # working client: the SessionStart hook is vendored
    assert (dest / ".claude" / "hooks" / "sync_pull.py").exists()

def test_install_prompt_fallback_errors_non_tty(monkeypatch, capsys):
    import tools.install as im
    monkeypatch.setattr(im.sys, "stdin", type("S", (), {"isatty": staticmethod(lambda: False)})())
    import pytest
    with pytest.raises(SystemExit):
        im._prompt_if_missing("", "email")
```

- [ ] **Step 2: Run to verify it fails** (ImportError on `install` / `_prompt_if_missing`).

- [ ] **Step 3: Implement** (add to `tools/install.py`)

```python
def install(remote_url, dest, name, email, role):
    problems = preflight(remote_url)
    if problems:
        for p in problems:
            print("PREFLIGHT: " + p, file=sys.stderr)
        raise SystemExit(1)
    dest = Path(dest)
    setup_client(remote_url, dest, name=name, email=email)
    handle = slugify(email.split("@")[0])
    write_profile(dest, name, role, handle)
    print(f"Installed client at {dest}.")
    print(f"  identity: {name} <{email}>   handle: {handle}   role: {role}")
    print("Next: point your AI assistant at this directory and run /onboarding.")
    return dest

def _prompt_if_missing(value, label):
    if value:
        return value
    if sys.stdin.isatty():
        return input(f"{label}: ").strip()
    print(f"error: --{label} is required (stdin is not a TTY)", file=sys.stderr)
    raise SystemExit(2)
```

- [ ] **Step 4: Run to verify it passes** (2 passed), then the whole suite.
- [ ] **Step 5: Commit** (`feat: install() provisions with real identity + seeded handle`).

---

## Task 5: `_mirror` + `update()` (code-only, mirror-with-delete)

**Files:** Modify `tools/install.py`; Test `tests/test_install.py`.

**Context:** `update` re-vendors only harness-owned code (`lib/`, `.claude/hooks/`, `settings.local.json`, `publish_allowlist.txt`), using mirror-with-delete so a file removed from the harness is removed on the client. It never touches `.claude/skills/`, `.claude/skills-local/`, `private/`, git identity, `.applied.json`, `.control-block`.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_install.py
from tools.install import update

def test_update_revendors_code_deletes_stale_preserves_local(bare_remote, tmp_path):
    dest = install(str(bare_remote), tmp_path / "c",
                   name="Ada", email="ada@x.com", role="eng")
    # simulate a client that has a STALE lib file no longer in the harness
    (dest / "lib" / "stale_module.py").write_text("# old\n")
    # local state that MUST be preserved
    (dest / "private" / "personal-context" / "keep.md").write_text("mine\n")
    (dest / ".applied.json").write_text('{"skills_version": 7}\n')
    (dest / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    (dest / ".claude" / "skills" / "materialized.md").write_text("from-control-plane\n")

    update(dest)

    # stale lib file removed by mirror-with-delete
    assert not (dest / "lib" / "stale_module.py").exists()
    # real harness lib files present
    assert (dest / "lib" / "freshness.py").exists()
    # local state preserved
    assert (dest / "private" / "personal-context" / "keep.md").read_text() == "mine\n"
    assert (dest / ".applied.json").read_text() == '{"skills_version": 7}\n'
    assert (dest / ".claude" / "skills" / "materialized.md").read_text() == "from-control-plane\n"
    # identity preserved
    assert run_git(dest, "config", "user.email").stdout.strip() == "ada@x.com"
```

- [ ] **Step 2: Run to verify it fails** (ImportError on `update`).

- [ ] **Step 3: Implement** (add to `tools/install.py`)

```python
def _mirror(src, dst):
    """Copy src tree into dst, deleting files in dst not present in src. Ignores
    __pycache__ on both sides."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    def files(base):
        return {p.relative_to(base) for p in base.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts}
    src_files = files(src)
    dst_files = files(dst)
    for rel in sorted(src_files):
        d = dst / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, d)
    for rel in sorted(dst_files - src_files):
        (dst / rel).unlink()

def update(dest):
    """Re-vendor only harness-owned client code; preserve all local state."""
    dest = Path(dest)
    _mirror(LIB, dest / "lib")
    _mirror(CLIENT_KIT / ".claude" / "hooks", dest / ".claude" / "hooks")
    shutil.copy2(CLIENT_KIT / ".claude" / "settings.local.json",
                 dest / ".claude" / "settings.local.json")
    shutil.copy2(CLIENT_KIT / "publish_allowlist.txt", dest / "publish_allowlist.txt")
    print(f"Updated client code at {dest} "
          "(private data, identity, and control-plane state preserved).")
    return dest
```

- [ ] **Step 4: Run to verify it passes** (1 passed), then the whole suite.
- [ ] **Step 5: Commit** (`feat: update() re-vendors client code via mirror-with-delete`).

---

## Task 6: CLI entrypoint + `/onboarding` skill + process-meeting tightening + e2e + docs

**Files:** Modify `tools/install.py` (CLI); Create `client-kit/skills/onboarding/SKILL.md`; Modify `client-kit/skills/process-meeting/SKILL.md`; Create `tests/test_install_e2e.py`; Modify `README.md`, `docs/getting-started.md`.

- [ ] **Step 1: Add the CLI** to the bottom of `tools/install.py`

```python
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Install or update a team-brain-harness client.")
    ap.add_argument("--update", metavar="DEST", help="update an existing client's code in place")
    ap.add_argument("remote_url", nargs="?", help="the live hive git URL")
    ap.add_argument("dest", nargs="?", help="where to create the client")
    ap.add_argument("--name"); ap.add_argument("--email"); ap.add_argument("--role")
    a = ap.parse_args()
    if a.update:
        update(a.update)
    elif a.remote_url and a.dest:
        name = _prompt_if_missing(a.name, "name")
        email = _prompt_if_missing(a.email, "email")
        role = _prompt_if_missing(a.role, "role")
        install(a.remote_url, a.dest, name, email, role)
    else:
        print("usage: python3 tools/install.py <remote-url> <dest> [--name N --email E --role R]\n"
              "       python3 tools/install.py --update <dest>", file=sys.stderr)
        raise SystemExit(2)
```

- [ ] **Step 2: Create `client-kit/skills/onboarding/SKILL.md`**

```markdown
---
name: onboarding
description: First-run interview that enriches your private personal-context profile (primary domain, current focus, what you work on) after the installer seeds your name, role, and handle.
---

# Onboarding

Run this once, right after installing your client, to complete your profile.

## Steps

1. **Read the seeded profile** at `private/personal-context/profile.md` (the installer wrote your name, `handle:`, and `role:`). Keep the `handle:` and `role:` lines intact.
2. **Interview the member** briefly: primary domain, current focus, what they own / work on, key collaborators.
3. **Enrich the profile** by adding those as prose under the existing header. Do not change the `handle:` line (it is the stable author identity used when you contribute meeting notes).
4. **Point them at the daily flow:** `/process-meeting` after meetings, `/hive-audit` to keep shared knowledge fresh, and publishing shared notes. The profile stays private (never synced); your role is a soft hint for emphasis, never an access restriction.
```

- [ ] **Step 3: Tighten `client-kit/skills/process-meeting/SKILL.md` step 4**

Replace the step-4 line:
```
4. **Determine your author-id** (one stable identity, used everywhere): a handle from your `private/personal-context` profile if you have one; otherwise the slugified local-part of `git config user.email` (e.g. `alice@x.com` -> `alice`).
```
with:
```
4. **Determine your author-id**: read the `handle:` field in `private/personal-context/profile.md` (seeded by the installer as the slugified local-part of your git email). If for some reason there is no profile, fall back to the slugified local-part of `git config user.email` (e.g. `alice@x.com` -> `alice`).
```

- [ ] **Step 4: Write the e2e test** `tests/test_install_e2e.py`

```python
import subprocess, sys
from pathlib import Path
from tools.instantiate import instantiate
from tools.install import install, update
from lib.gitsync import run_git

def _bare_from(local, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def test_install_then_hook_runs_then_update(tmp_path):
    hive = instantiate(tmp_path / "hive")
    remote = _bare_from(hive, tmp_path)
    client = install(str(remote), tmp_path / "client",
                     name="Ada", email="ada@x.com", role="eng")

    # the installed client's SessionStart hook runs cleanly (real identity, not blocked)
    r = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    # the /onboarding skill reached the client via the CONTROL/skills mirror
    assert (client / ".claude" / "skills" / "onboarding" / "SKILL.md").exists()

    # update re-vendors code; the vendored version matches the harness
    update(client)
    assert (client / "lib" / "version.py").read_text() == (Path(__file__).resolve().parents[1] / "lib" / "version.py").read_text()
```

- [ ] **Step 5: Run the e2e + full suite.** Debug until green. (`instantiate` vendors `client-kit/skills` -> `CONTROL/skills`, so `onboarding` propagates like `process-meeting`/`hive-audit`; `install` -> `setup_client` -> `sync_skills` materializes it into `.claude/skills`.)

- [ ] **Step 6: Docs**
- `README.md`: status badge -> `5%2F5%20sub--projects%20(complete)` (or similar "complete"); tests badge to the final count (run the suite, use the number, also fix the in-prose count); the member quick start uses `python3 tools/install.py <hive-url> <dest> --name --email --role`; the Status section marks all five sub-projects done (the harness is feature-complete); add an installer/onboarding bullet under How it works.
- `docs/getting-started.md`: rewrite Part B to use `install.py` (with flags and the SSH-key note), add a "Keeping your client up to date" subsection (`python3 tools/install.py --update <clone>`), and add the `/onboarding` first-run step. Add command-reference rows: "Install a member client" -> `python3 tools/install.py <hive-url> <dest> --name --email --role`; "Update your client code" -> `python3 tools/install.py --update <clone>`; "Finish your profile (first run)" -> run the `/onboarding` skill. (Keep the existing `setup_client` row or note install.py is the recommended member path.)

- [ ] **Step 7: Run the full suite + commit** (`feat: install CLI + /onboarding skill; tighten process-meeting handle; test: installer e2e; docs: mark harness complete`).

---

## Final: after all tasks

- [ ] Run the full suite once more: `cd /Users/stas.wishnevetsky/team-brain-harness && ./.venv/bin/python -m pytest -q` (all green).
- [ ] Use **superpowers:finishing-a-development-branch**. Given `main` is branch-protected, the expected path is **Option 1 (push and open a PR)** for your own review/merge. This is the final sub-project; the PR completes the harness.
