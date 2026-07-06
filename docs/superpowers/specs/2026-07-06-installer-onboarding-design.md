# Full installer + onboarding (sub-project 5)

> The final sub-project of the group hive brain. Builds on sub-projects 1-4 and implements master-design section 5 (Onboarding) and section 6 (Rollout) ([2026-07-03-group-hive-brain-design.md](2026-07-03-group-hive-brain-design.md)). Completes the roadmap.

## 1. Context and goals

Today a member is provisioned by `tools/setup_client.py`, described in its own docstring as a "minimal stand-in for the full installer" (it even hardcodes `member@example.com`). This sub-project delivers the polished, member-facing installer and first-run onboarding that master section 5 promises: preflight checks, SSH guidance, real identity + role capture, provisioning, an update path, and a first-run interview that seeds the member's profile.

**Goal:** a member (including a non-technical one) runs one command to stand up a working client with their real identity and role, gets clear guidance for the one manual step (registering an SSH key), can later run the same tool to update their vendored client code, and completes a first-run `/onboarding` interview that seeds their private profile. All client-side, stdlib only, no server.

## 2. Non-goals and constraints

- **Does not install the AI client (Claude Code) itself.** That is assumed present; the installer provisions the hive client (clone + vendored hooks/lib + private tree).
- **Detect-and-guide SSH only.** The installer never writes `~/.ssh`; it verifies GitHub SSH reachability and, on failure, prints instructions for the member to generate and register a key. The one manual responsibility is registering the printed/how-to key.
- **No new runtime dependency.** Stdlib only, consistent with the rest of the harness.
- **Update preserves local state.** `--update` re-vendors only client code; it never touches `private/`, identity, or control-plane bookkeeping.
- **Roles are soft affinity, not access control** (as decided in sub-project 3): the profile guides assistant emphasis, never restricts.

## 3. Key decisions

### 3.1 Scope: installer orchestrator + update mode + onboarding skill
Build `tools/install.py` (a member-facing orchestrator over the existing `setup_client` provisioning) with an install mode and an `--update` mode, plus a thin `/onboarding` skill. Installing Claude Code itself is out of scope.

### 3.2 SSH: detect-and-guide only
The installer verifies `ssh -T git@github.com` reachability and, on failure, prints step-by-step guidance (generate an ed25519 key, paste the public key at `github.com/settings/keys`, re-run). It never generates keys or writes `~/.ssh`. This is safer and more testable, at the cost of one extra manual step for the member.

### 3.3 Identity/role: flags with interactive fallback
`--name`, `--email`, `--role` flags make the installer scriptable (admin batch-provisioning) and unit-testable; when a required value is missing and stdin is a TTY, the installer prompts. The real git identity is written into the clone (fixing the hardcoded placeholder, which drives the author-id used by meeting roll-up and freshness stamps).

### 3.4 Update: re-vendor code only, preserve all local state
`--update` overwrites only the vendored client code (`lib/`, `.claude/`, `publish_allowlist.txt`) from the harness into an existing clone; it preserves `private/`, the git identity, `.applied.json`, and `.control-block`. It does not re-clone, re-seed `.applied.json`, or touch shared content. This is the concrete resolution of a control-plane `min_client_version` gate.

### 3.5 Profile: installer seeds minimal, `/onboarding` enriches
The installer writes a minimal `private/personal-context/profile.md` (name + role) via a deterministic `lib/profile.py` helper; the thin `/onboarding` skill enriches the same file (primary domain, focus, what they work on) with assistant judgment. The profile is a private local note, never synced, and not freshness-tracked (no `last_verified`) so it never nags.

## 4. Architecture

### 4.1 New module: `tools/install.py`
Member-facing orchestrator; importable functions plus a CLI.
- `ssh_ok() -> bool` — run `ssh -T git@github.com`; return True when stderr contains the GitHub `"successfully authenticated"` banner (the command exits non-zero even on success, so exit code is not used). Small and separately mockable.
- `preflight(remote_url) -> list[str]` — return a list of problem strings (empty = OK): git missing (`shutil.which("git")` is None), Python < 3.11 (`sys.version_info`), and, **only when `remote_url` is a GitHub SSH URL** (`git@github.com:...`), `not ssh_ok()`. For a local/file remote or a non-GitHub host the SSH check is skipped (so tests against a local bare remote pass without network).
- `install(remote_url, dest, name, email, role) -> Path` — run preflight; on an SSH problem print guidance and raise/exit (member re-runs after registering a key); else provision via `setup_client(remote_url, dest, name=name, email=email)`, then `write_profile(dest, name, role)`, then print next steps. Idempotent enough to re-run (setup_client uses `dirs_exist_ok`; profile rewrite is idempotent).
- `update(dest) -> Path` — re-vendor `lib/`, `.claude/`, `publish_allowlist.txt` from the harness `ROOT` into `dest` (via `shutil.copytree(..., dirs_exist_ok=True)` / `copy2`); do nothing else. Preserves `private/`, git identity, `.applied.json`, `.control-block`.
- `__main__` CLI: `python3 tools/install.py <remote-url> <dest> [--name N] [--email E] [--role R]` for install; `python3 tools/install.py --update <dest>` for update. A missing required flag prompts when `sys.stdin.isatty()`, else errors with a clear message.

### 4.2 New module: `lib/profile.py`
- `write_profile(dest, name, role) -> Path` — write `<dest>/private/personal-context/profile.md` atomically (temp + `os.replace`), creating the dir if needed. Minimal seed content:
  ```markdown
  # <name>

  - role: <role>

  (Run /onboarding to add your primary domain, current focus, and what you work on.)
  ```
  No `last_verified` front-matter (so the freshness check never flags a member's own profile). Idempotent: re-running rewrites the same content; the `/onboarding` skill enriches the file afterward.

### 4.3 `setup_client` parametrization
`setup_client(remote_url, dest, name="Member", email="member@example.com")` sets `git config user.name`/`user.email` from the parameters. The defaults preserve every existing two-argument caller and test; `install.py` passes the member's real name/email, so the author-id (derived from the git email local-part by meeting roll-up and freshness) is correct. No other behavior changes.

### 4.4 The `/onboarding` skill
`client-kit/skills/onboarding/SKILL.md`, vendored into `CONTROL/skills/` by `instantiate` and delivered to clients by the sub-project-3 skills mirror (same path as `process-meeting` and `hive-audit`). Steps: read the installer-seeded `profile.md` (name + role); interview the member (primary domain, current focus, what they work on/own, key collaborators); enrich `profile.md` in prose; point them at the daily flow (`/process-meeting`, `/hive-audit`, publishing). The profile stays private; roles remain soft affinity.

### 4.5 Session-start compatibility
The installer changes nothing about the SessionStart hook. It only affects provisioning and the local git identity/profile. An installed client behaves exactly as a `setup_client`-provisioned one, with a real identity instead of the placeholder.

## 5. Testing

- **Unit:** `write_profile` (creates `private/personal-context/profile.md` with the name/role, atomic, idempotent, contains no `last_verified`); `preflight` (git-missing yields a problem via a monkeypatched `shutil.which`; SSH check is skipped for a local/`file:`/non-GitHub URL; SSH check is invoked and surfaced for a `git@github.com:` URL via a mocked `ssh_ok`); the CLI's flag/interactive-fallback (a missing required value with a non-TTY stdin produces a clear error, not a hang).
- **Integration** (temp git repos, local `bare_remote` so the SSH check is not triggered): `install(remote, dest, name="Ada", email="ada@x.com", role="eng")` clones, sets the real identity (assert `git config user.email` == `ada@x.com`), seeds `profile.md` (contains "Ada" and "eng"), and yields a working client (the SessionStart hook file exists and `.applied.json` is seeded); `update(dest)` re-vendors `lib/`/`.claude/`/`publish_allowlist.txt` while a sentinel file under `private/`, the git identity, and a hand-edited `.applied.json` are all preserved byte-for-byte.
- **End-to-end:** `install` a client against an instantiated hive, run its `sync_pull` hook (succeeds: real identity, not blocked); then simulate a newer harness (bump `lib/version.py` `CLIENT_VERSION` in a copy, or assert the vendored version matches `ROOT`'s after update) and run `update(dest)`, asserting the vendored `lib/version.py` matches the harness and the preserved local state survived.

## 6. Open questions and risks

- **SSH reachability is not unit-testable offline.** `ssh_ok` contacts GitHub, so it is mocked in tests; the URL-gating means local-remote integration/e2e tests never invoke it. Real SSH verification only happens in actual member use. Accepted: the logic around it (git/Python checks, URL gating, guidance message) is fully tested.
- **`update` staleness of identity/profile.** `update` deliberately does not touch identity or the profile; if a member's email changes, they re-run install or fix `git config` manually. Accepted (rare).
- **Interactive prompts in non-TTY contexts.** The installer must never hang waiting on stdin in CI/scripts; a missing required value with a non-TTY stdin is a hard error, not a prompt. Tested.
- **Non-technical SSH step.** Detect-and-guide (not auto-generate, per 3.2) leaves key generation to the member; the admin assists, as master section 6's rollout anticipates. Accepted tradeoff for not writing `~/.ssh`.

## 7. Relationship to existing artifacts

Implements master sections 5 and 6. Wraps and lightly parametrizes `tools/setup_client.py`; reuses the sub-project-3 `CONTROL/skills` distribution channel for the `/onboarding` skill; the real identity it sets flows into the sub-project-2 roll-up and sub-project-4 freshness author-id. `--update` closes the sub-project-3 control-plane `min_client_version` loop. This is the last sub-project: on merge, the harness implements all five (walking skeleton, meeting roll-up, control plane, freshness, installer/onboarding) and reads as a finished product.
