# Control plane + client update mechanism (sub-project 3)

> Sub-project 3 of the group hive brain. Builds on the walking skeleton (sub-project 1) and meeting roll-up (sub-project 2), and implements sections 3.6, 4.5, and 4.9 of the master design ([2026-07-03-group-hive-brain-design.md](2026-07-03-group-hive-brain-design.md)).

## 1. Context and goals

The hive already syncs shared knowledge and rolls up meetings, but there is no way for an admin to evolve the system: push a new shared skill, change the directory structure, require a new MCP, or raise the minimum client version, and have every member's client pick it up automatically and safely. Today `CONTROL/manifest.json` exists but nothing reads it.

This sub-project builds the **control plane**: the admin edits `CONTROL/` and pushes; each client, on its next session-start pull, reconciles its local state against the manifest and applies what changed, in a safe order, gating itself when it is too old to proceed. It also gives the admin a **purge** tool to scrub leaked private data from history.

**Goal:** an admin changes `CONTROL/` and pushes; every client converges on the next session start, applying skills, structure migrations, policy, and MCP announcements deterministically and idempotently, halting safely when a gate is unmet, with no server and no separate push-to-clients channel.

## 2. Non-goals and constraints

- **No server, no CI, no push channel.** Distribution is git: the admin commits to `CONTROL/`; clients reconcile on pull. Consistent with the master design.
- **No arbitrary remote code execution.** Migrations are declarative JSON over a fixed op set, never repo-sourced code run on clients.
- **Client code is vendored, not git-synced.** `lib/` and hooks are copied into a client at provision time and gitignored; only shared *data* (skills, migrations, policy, manifest) flows through git. Satisfying a `min_client_version` bump therefore means re-vendoring the client code, not a pull.
- **A session-start hook cannot hard-lock the assistant.** A gate is a safe-halt (apply nothing) plus a loud notice plus a standing policy instruction, not a true lock.
- **Stdlib only** (no new runtime dependencies), consistent with the rest of the harness.

## 3. Key decisions

### 3.1 Scope: full client-update mechanism + purge tooling
Build the whole reconciliation engine (manifest vs `.applied.json`, gate evaluation, declarative structure migrations, skills mirror, policy reload, MCP announcement, client version) wired into the session-start hook, plus a scripted admin **purge** tool. Admin **prune** (reorganizing non-sensitive shared content) stays ordinary commits and migrations, with no special tool.

### 3.2 Gate semantics: safe-halt + loud notice + policy
A session-start hook cannot lock the assistant, so a gate is defined by what the hook can enforce: on an unmet gate the hook applies nothing (no migrations, no skills sync, no roll-up), writes a client-local `.control-block` sentinel, prints a prominent BLOCKED notice with the exact fix command, and emits a standing policy line instructing the assistant to refuse substantive shared-vault work until the block clears. The session still runs, but it is loudly halted and the vault is protected from a too-old client.

### 3.3 Client version: a constant in vendored lib code
`lib/version.py` holds `CLIENT_VERSION`. Because `setup_client` vendors all of `lib/`, the version travels with the code; re-vendoring updated `lib/` updates the version in lockstep. The `min_client_version` gate compares the manifest value against `CLIENT_VERSION` with a stdlib semver-lite tuple compare.

### 3.4 Migrations: declarative JSON ops
Each structure migration is `CONTROL/migrations/NNNN-slug.json` = `{"breaking": bool, "ops": [...]}` over a fixed, idempotent op set (`make_dir`, `move`/`rename`, `delete`, `keep_file`). A runner interprets the ops; no repo-sourced code executes on clients. This covers directory-structure changes (the stated use case) and is safe-by-construction for multi-client sync.

### 3.5 Skills sync: full mirror of the shared set only
`.claude/skills/` is made an exact mirror of `CONTROL/skills/` (add, update, delete). `.claude/skills-local/` (personal, gitignored) is never read or touched, so members' private skills are safe. This makes `CONTROL/skills/` the single canonical home for shared skills and completes the `/process-meeting` relocation deferred in sub-project 2.

## 4. Architecture

### 4.1 New module: `lib/control_plane.py`
Pure-ish functions plus one orchestrator:
- `version_tuple(s) -> tuple[int, ...]` and a compare helper (semver-lite; versions like `"0.0.1"`).
- `read_manifest(repo) -> dict`; `read_applied(repo) -> dict` (missing file -> all-zero / empty `announced_mcps`); `write_applied(repo, applied)`.
- `pending_migrations(repo, applied) -> list[Path]` (migrations whose `NNNN > applied["structure_version"]`, sorted by `NNNN`).
- `evaluate_gate(manifest, client_version, pending) -> list[str]` -> gate reasons (empty = clear).
- `apply_migration(repo, migration) -> None` (interpret ops idempotently; reject paths containing `..` or absolute paths).
- `sync_skills(repo) -> dict` (mirror `CONTROL/skills/` -> `.claude/skills/`; report added/updated/deleted).
- `reload_policy(repo) -> str` (read `CONTROL/policy.md`; empty string if absent).
- `mcp_announcements(manifest, applied) -> list[dict]` (entries in `required_mcps` whose `name` is not in `applied["announced_mcps"]`).
- `apply_control_plane(repo) -> ControlResult` (the orchestrator; see 4.3).

`ControlResult` reports: `blocked` (bool) + `gate_reasons`, and when applied: `migrations_applied`, `skills_changed`, `policy_text`, `mcp_announcements`.

### 4.2 New module: `lib/version.py`
`CLIENT_VERSION = "0.0.1"`. Single source of the client's own version.

### 4.3 Reconciliation flow (session start, after `pull`)
1. Read manifest, `.applied.json` (missing -> zeros/empty), `CLIENT_VERSION`; compute `pending_migrations`.
2. `evaluate_gate`: gate reasons include `CLIENT_VERSION < min_client_version`. A pending migration flagged `breaking` is bound to its accompanying `min_client_version` bump (3.4 / 4.4), so it is enforced by this same gate rather than as an independent, never-clearing condition.
3. **If gated:** write `.control-block` with the reasons, print the BLOCKED notice + fix command, emit the standing policy line, apply nothing, skip roll-up. Return `blocked=True`.
4. **If clear:** remove any stale `.control-block`, then apply in order, writing `.applied.json` after each step succeeds (so an interrupted pull resumes cleanly next session):
   1. structure migrations (each, then bump `applied["structure_version"]` to that `NNNN`)
   2. skills mirror if `manifest.skills_version != applied.skills_version`, then set `applied.skills_version`
   3. policy reload if `manifest.policy_version != applied.policy_version`, then set `applied.policy_version`; emit `policy.md` into context
   4. MCP announcements for new names, then append them to `applied.announced_mcps`
5. The existing roll-up (`roll_up_all`) then runs.

### 4.4 Migration semantics
- `CONTROL/migrations/NNNN-slug.json`, `NNNN` a zero-padded integer establishing total order.
- Ops (all idempotent; a no-op if already in the target state): `make_dir(path)`, `move(from, to)` (alias `rename`), `delete(path)`, `keep_file(path)` (ensure an empty tracked file). Paths are repo-relative; `..` and absolute paths are rejected so a migration cannot escape the vault.
- Pending = `NNNN > applied.structure_version`; applied in ascending order; `applied.structure_version` advanced to the highest applied `NNNN`.
- `breaking: true` asserts "this migration requires the `min_client_version` bump shipped with it." The runner never applies a pending breaking migration while `CLIENT_VERSION < min_client_version` (that is the gate); once the client is new enough, all pending migrations, breaking or not, apply. This keeps `breaking` a real hard barrier for a too-old client without creating a gate that can never clear.

### 4.5 Skills mirror
`sync_skills` walks `CONTROL/skills/` and `.claude/skills/` and reconciles the latter to match the former: copy new and changed skill files/dirs, delete anything in `.claude/skills/` not present in `CONTROL/skills/`. `.claude/skills-local/` is out of scope and untouched. Runs on `skills_version` change and once at provision time.

### 4.6 Policy and MCP announcements
- `CONTROL/policy.md` is standing instructions emitted into session context. It carries the block clause: "if `.control-block` exists, refuse substantive shared-vault work until it clears." The hook emits policy content each session; a `policy_version` change is what advances `.applied.json` (the emission itself is unconditional so the standing instructions are always in context).
- `required_mcps` entries are `{name, how}`. Names not in `applied.announced_mcps` are announced with their `how` string (auth is a human step; the client announces, never auto-configures), then recorded.

### 4.7 Client-local state
`.applied.json` and `.control-block` live in the client clone, are gitignored (added to `.git/info/exclude` by `setup_client`), and never sync. `.applied.json` is the per-client record of applied versions; `.control-block` is the gate sentinel.

### 4.8 Admin purge tool: `tools/purge.py`
`python3 tools/purge.py <path> [--force]` scrubs a path from all git history when private data leaks into the shared tree.
- Dry run by default (prints what would be removed and the follow-up runbook); `--force` executes.
- Uses `git filter-branch --index-filter 'git rm -r --cached --ignore-unmatch <path>'` across all history (filter-branch is always available; filter-repo is not installed in this environment).
- On completion prints the mandatory runbook: force-push the rewritten history, tell every member to re-clone (history changed), and rotate any exposed secret.

### 4.9 Hook wiring
`client-kit/.claude/hooks/sync_pull.py`, after `pull` and before `roll_up_all`, calls `apply_control_plane(repo)`. If `blocked`, it prints the BLOCKED notice and the policy block-line and returns without rolling up. Otherwise it prints a concise applied-summary (migrations, skills changes, MCP announcements), emits the policy text, then proceeds to `roll_up_all`.

### 4.10 setup_client / instantiate changes
- `setup_client`: after clone + vendoring `.claude` and `lib/`, run `sync_skills(dest)` to seed `.claude/skills/` from `CONTROL/skills/`; seed `.applied.json` to the current manifest (`skills_version`, `structure_version` = highest existing migration `NNNN` or the manifest value, `policy_version`, `announced_mcps` = current `required_mcps` names) so a fresh client starts current and does not replay history; add `.applied.json` and `.control-block` to `.git/info/exclude`.
- `instantiate`: unchanged in logic; the template now carries `CONTROL/policy.md`, `CONTROL/migrations/`, and `CONTROL/skills/`, and it already vendors `client-kit/skills/` into `CONTROL/skills/`.
- **Relocate** `/process-meeting` from `client-kit/.claude/skills/process-meeting/` to `client-kit/skills/process-meeting/` so it is vendored into `CONTROL/skills/` and reaches clients via the mirror. `setup_client` no longer bundles it directly (the mirror does).

## 5. Testing

- **Unit:** `version_tuple` / compare; `evaluate_gate` (too-old blocks, current passes, breaking-under-old blocks, breaking-under-current allowed); each migration op idempotent and path-escape rejected; `sync_skills` add / update / delete and skills-local untouched; `mcp_announcements` diff; `reload_policy` read/empty; `read_applied` default when missing.
- **Integration** (temp git repos): apply a pending migration end-to-end and confirm the tree changed and `.applied.structure_version` advanced; a gated session applies nothing, writes `.control-block`, and skips roll-up; skills mirror deletes a skill removed from CONTROL; `.applied.json` written per step so an interrupted run resumes; MCP announced once then not again.
- **Purge:** on a temp repo with a committed secret path, `purge.py --force` removes it from all history (`git log --all -- <path>` empty afterward).
- **End-to-end:** admin bumps the manifest (new skill + a migration + a new MCP + policy) and pushes; a client's `sync_pull` session-start converges (skill present, structure changed, MCP announced, policy in output); a second run is a clean no-op.

## 6. Open questions and risks

- **filter-branch performance/deprecation.** `git filter-branch` is slow and deprecated in favor of `git filter-repo`, which is not installed here. Acceptable because purge is rare; if `filter-repo` becomes available the tool can prefer it.
- **Gate false-positives.** If an admin ships a breaking migration without bumping `min_client_version`, the gate will not fire and an old client may apply it. Mitigated by convention and admin governance (CODEOWNERS on `CONTROL/`); documented in `policy.md`.
- **Skills mirror deleting a skill a member is mid-using.** Full mirror deletes retired skills on next sync; acceptable because shared skills are admin-governed and personal work lives in `skills-local`.

## 7. Relationship to existing artifacts

Implements master-design sections 3.6, 4.5, 4.9. Reuses `lib/gitsync.py` (`pull`, `push_paths`) and slots into the existing SessionStart hook between pull and roll-up. Completes the `CONTROL/skills/` distribution channel deferred in sub-project 2. Leaves TTL/freshness (sub-project 4) and the full installer/onboarding (sub-project 5) untouched.
