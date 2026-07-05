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

### 3.4 Migrations: declarative JSON ops, committed as a transaction
Each structure migration is `CONTROL/migrations/NNNN-slug.json` = `{"min_client_version": "x.y.z" | null, "ops": [...]}` over a fixed, idempotent op set (`make_dir`, `move`/`rename`, `delete`, `keep_file`). A runner interprets the ops; no repo-sourced code executes on clients. Because migrations restructure **shared, tracked** content, the runner commits and pushes the migrated tree as its own git transaction (mirroring the roll-up transaction), so the change converges in the repo rather than living in one client's working tree. Idempotency means a client that pulls an already-migrated tree re-runs the ops to an empty diff and simply advances its local bookkeeping. This covers directory-structure changes (the stated use case) and is safe-by-construction for multi-client sync. `min_client_version` on a migration replaces a fuzzy "breaking" boolean with an enforceable, non-deadlocking gate (3.2 / 4.4).

### 3.5 Skills sync: full mirror of the shared set only
`.claude/skills/` is made an exact mirror of `CONTROL/skills/` (add, update, delete). `.claude/skills-local/` (personal, gitignored) is never read or touched, so members' private skills are safe. This makes `CONTROL/skills/` the single canonical home for shared skills and completes the `/process-meeting` relocation deferred in sub-project 2.

## 4. Architecture

### 4.1 New module: `lib/control_plane.py`
Pure-ish functions plus one orchestrator:
- `version_tuple(s) -> tuple[int, ...]` and a compare helper (semver-lite; versions like `"0.0.1"`).
- `read_manifest(repo) -> dict`; `read_applied(repo) -> dict` (missing file -> all-zero / empty `announced_mcps`); `write_applied(repo, applied)`.
- `pending_migrations(repo, applied) -> list[Path]` (migrations whose `NNNN > applied["structure_version"]`, sorted by `NNNN`).
- `evaluate_gate(manifest, client_version, pending) -> list[str]` -> gate reasons (empty = clear): `client_version < manifest.min_client_version`, plus `client_version < m.min_client_version` for any pending migration `m`.
- `apply_migration(repo, migration) -> bool` (interpret ops idempotently; enforce path containment per 4.4; return whether the working tree changed). Committing/pushing the change is the orchestrator's job (4.3 step 4.1), mirroring how `roll_up` leaves the git transaction to `roll_up_all`.
- `sync_skills(repo) -> dict` (mirror `CONTROL/skills/` -> `.claude/skills/`; report added/updated/deleted).
- `reload_policy(repo) -> str` (read `CONTROL/policy.md`; empty string if absent).
- `mcp_announcements(manifest, applied) -> list[dict]` (entries in `required_mcps` whose `name` is not in `applied["announced_mcps"]`).
- `apply_control_plane(repo) -> ControlResult` (the orchestrator; see 4.3).

`ControlResult` reports: `blocked` (bool) + `gate_reasons`, and when applied: `migrations_applied`, `skills_changed`, `policy_text`, `mcp_announcements`.

### 4.2 New module: `lib/version.py`
`CLIENT_VERSION = "0.0.1"`. Single source of the client's own version.

### 4.3 Reconciliation flow (session start, after `pull`)
1. Read manifest, `.applied.json` (missing -> zeros/empty), `CLIENT_VERSION`; compute `pending_migrations`.
2. `evaluate_gate`: gate reasons = `CLIENT_VERSION < manifest.min_client_version` OR, for any pending migration, `CLIENT_VERSION < migration.min_client_version`. Because the gate is a version comparison, re-vendoring the client to a newer `CLIENT_VERSION` always clears it (non-deadlocking).
3. **If gated:** write `.control-block` (atomic write) with the reasons, print the BLOCKED notice + fix command, emit the standing policy line, apply nothing, skip roll-up. Return `blocked=True`.
4. **If clear:** remove any stale `.control-block`, then apply in order. Every `.applied.json` update is an atomic write-then-rename, performed only after that step's side effects are durable, so an interrupted pull resumes cleanly next session:
   1. **structure migrations** (ascending `NNNN`): apply the ops; if the working tree changed, commit and push the migrated shared paths as a transaction (fetch-rebase-retry via `push_paths`); on an unrecoverable push conflict, `git reset --hard <remote-tip>` and defer (leave `applied.structure_version` unchanged so it retries next session). Only after the commit lands (or the ops were a no-op against an already-migrated tree) advance `applied.structure_version` to that `NNNN`.
   2. **skills mirror** if `manifest.skills_version != applied.skills_version` (writes only the client-local `.claude/skills/`; nothing to commit), then set `applied.skills_version`.
   3. **policy reload** if `manifest.policy_version != applied.policy_version`, then set `applied.policy_version`; emit `policy.md` into context.
   4. **MCP announcements** for new names, then append them to `applied.announced_mcps`.
5. The existing roll-up (`roll_up_all`) then runs. Because migrations are already committed by step 4.1, `roll_up_all`'s repo-wide `reset --hard <remote-tip>` on a meeting conflict cannot destroy migration work (it is at the remote tip), and it never touches gitignored `.claude/` (the skills mirror).

### 4.4 Migration semantics
- File: `CONTROL/migrations/NNNN-slug.json`, `NNNN` a zero-padded integer establishing total order; body `{"min_client_version": "x.y.z" | null, "ops": [...]}`.
- **Target = shared, tracked content.** The runner applies ops to the working tree, then commits and pushes the changed shared paths as a transaction (4.3 step 4.1). Convergence lives in the repo, not a single working tree.
- **Ops (fixed, individually idempotent under partial re-application):**
  - `make_dir(path)`: create dir; no-op if it exists.
  - `move(from, to)` (alias `rename`): defined for all four quadrants: (from exists, to absent) -> move; (from absent, to exists) -> no-op (already done); (from absent, to absent) -> no-op (assume done); (from exists, to exists) -> raise (ambiguous/collision; refuse rather than clobber).
  - `delete(path)`: remove; no-op if absent.
  - `keep_file(path)`: ensure an empty tracked file exists; no-op if present.
- **Path containment:** every `path`/`from`/`to` is repo-relative; reject `..`, absolute paths, and (after resolving symlinks) any final path that is not inside the shared tracked tree. `private/`, `.claude/`, and other client-local/gitignored areas are off-limits, so a migration can never touch private or local content.
- **Pending / bookkeeping:** pending = `NNNN > applied.structure_version`; applied in ascending order; a crash mid-migration leaves `applied.structure_version` un-advanced, so the whole migration re-runs next session (safe because every op is idempotent). `applied.structure_version` advances to the highest fully applied `NNNN`.
- **Gate:** a migration's optional `min_client_version` gates the session while `CLIENT_VERSION < migration.min_client_version` (4.3 step 2). This is enforced entirely client-side from data in the migration file, so it does not depend on the admin also bumping the global `manifest.min_client_version`; and because it is a version compare, updating the client clears it.

### 4.5 Skills mirror
`.claude/skills/` is a **client-local derived mirror** of the tracked `CONTROL/skills/`, not itself tracked: it is materialized from `CONTROL/skills/` and is gitignored on the client (via the vendored `/.claude/` exclude), so it is never committed or pushed. This supersedes the master design's 4.2 description of `.claude/skills/` as "tracked": the tracked canonical copy is `CONTROL/skills/`, and each client materializes a local mirror.

`sync_skills` walks `CONTROL/skills/` and `.claude/skills/` and reconciles the latter to match the former: copy new and changed skill files/dirs, delete anything in `.claude/skills/` not present in `CONTROL/skills/`. `.claude/skills-local/` (personal, gitignored) is out of scope and untouched. Runs on `skills_version` change and once at provision time.

### 4.6 Policy and MCP announcements
- `CONTROL/policy.md` is standing instructions emitted into session context. It carries the block clause: "if `.control-block` exists, refuse substantive shared-vault work until it clears." The hook emits policy content each session; a `policy_version` change is what advances `.applied.json` (the emission itself is unconditional so the standing instructions are always in context).
- `required_mcps` entries are `{name, how}`. Names not in `applied.announced_mcps` are announced with their `how` string (auth is a human step; the client announces, never auto-configures), then recorded.

### 4.7 Client-local state
`.applied.json` (per-client record of applied versions) and `.control-block` (gate sentinel) live in the client clone and must never sync. They are guarded two ways: **committed** in `hive-template/.gitignore` as `/.applied.json` and `/.control-block` (so every clone inherits the ignore, the primary guard), and added to `.git/info/exclude` by `setup_client` (defense-in-depth). The publish allowlist lists only shared content directories, so neither file can be staged by a publish. Both are written atomically (temp file + `os.replace`) so a crash never corrupts them.

### 4.8 Admin purge tool: `tools/purge.py`
`python3 tools/purge.py <path> [--force]` scrubs a path from all git history when private data leaks into the shared tree.
- Dry run by default (prints what would be removed and the follow-up runbook); `--force` executes.
- Uses `git filter-branch --index-filter 'git rm -r --cached --ignore-unmatch <path>'` over **all refs** (`-- --all`) so tags and every branch are rewritten (filter-branch is always available; filter-repo is not installed here).
- **Fully removes the blob, not just the path from the tip:** after filtering, drop the `refs/original/` backups, expire the reflog (`git reflog expire --expire=now --all`), and `git gc --prune=now`. Only then is the object unrecoverable. The purge test must run this cleanup before asserting the blob is gone (checking `git log --all -- <path>` alone would pass while the object is still recoverable).
- On completion prints the mandatory runbook: force-push the rewritten history, tell every member to re-clone (rewritten history diverges from their clones), and rotate any exposed secret. Notes the coordination window: a member mid-push during the force-push can reintroduce the blob, so the admin should announce the purge and confirm quiet before force-pushing.

### 4.9 Hook wiring
`client-kit/.claude/hooks/sync_pull.py`, after `pull` and before `roll_up_all`, calls `apply_control_plane(repo)`. If `blocked`, it prints the BLOCKED notice and the policy block-line and returns without rolling up. Otherwise it prints a concise applied-summary (migrations, skills changes, MCP announcements), emits the policy text, then proceeds to `roll_up_all`.

### 4.10 setup_client / instantiate changes
- `setup_client`: after clone + vendoring `.claude` and `lib/`, run `sync_skills(dest)` to seed `.claude/skills/` from `CONTROL/skills/`; seed `.applied.json` to the current state (`skills_version`, `structure_version` = highest existing migration `NNNN`, `policy_version`, `announced_mcps` = current `required_mcps` names) so a fresh client starts current and does not replay history; add `.applied.json` and `.control-block` to `.git/info/exclude`. Seeding `structure_version` high is safe precisely because migrations commit their tree changes as they run (4.4), so a fresh clone already carries the post-migration structure; there is no work to replay, only bookkeeping to skip.
- `instantiate`: unchanged in logic; the template now carries `CONTROL/policy.md`, `CONTROL/migrations/`, and `CONTROL/skills/`, and it already vendors `client-kit/skills/` into `CONTROL/skills/`.
- **Relocate** `/process-meeting` from `client-kit/.claude/skills/process-meeting/` to `client-kit/skills/process-meeting/` so it is vendored into `CONTROL/skills/` and reaches clients via the mirror. `setup_client` no longer bundles it directly (the mirror does).

## 5. Testing

- **Unit:** `version_tuple` / compare; `evaluate_gate` (too-old blocks, current passes, per-migration `min_client_version` too-old blocks, current allowed); each migration op idempotent including all four `move` quadrants (incl. from-exists+to-exists raises); path containment rejects `..`, absolute, symlink-escape, and `private/`/`.claude/` targets; `sync_skills` add / update / delete and skills-local untouched; `mcp_announcements` diff; `reload_policy` read/empty; `read_applied` default when missing; atomic write (interrupted write leaves prior file intact).
- **Integration** (temp git repos): apply a pending migration end-to-end and confirm the tree changed, the change was **committed and pushed** to the remote, and `.applied.structure_version` advanced; a second client that pulls the migrated tree re-runs the migration to an empty diff (no commit) and just advances its bookkeeping; a gated session applies nothing, writes `.control-block`, and skips roll-up; control-plane applied before roll-up survives a `roll_up_all` conflict-reset (migration commit persists); skills mirror deletes a skill removed from CONTROL; `.applied.json` written per step so an interrupted run resumes; MCP announced once then not again.
- **Purge:** on a temp repo with a committed secret path, `purge.py --force` rewrites all refs, drops `refs/original`, expires the reflog, and gc-prunes; afterward the blob is unrecoverable (verified by `git rev-list --all --objects` / cat-file, not just `git log`).
- **End-to-end:** admin bumps the manifest (new skill + a migration + a new MCP + policy) and pushes; a client's `sync_pull` session-start converges (skill present, structure changed and committed, MCP announced, policy in output); a second run is a clean no-op.

## 6. Open questions and risks

- **filter-branch performance/deprecation.** `git filter-branch` is slow and deprecated in favor of `git filter-repo`, which is not installed here. Acceptable because purge is rare; if `filter-repo` becomes available the tool can prefer it.
- **Migration gate is per-migration, not global.** The gate now reads `min_client_version` from the migration file itself (4.4), so it is enforced client-side without relying on the admin also bumping the global `manifest.min_client_version`. A migration that needs a newer client simply carries that requirement; an admin who omits it gets no gate (the migration is treated as safe for any client), which is the correct default for a purely-additive change.
- **Skills mirror deleting a skill a member is mid-using.** Full mirror deletes retired skills on next sync; acceptable because shared skills are admin-governed and personal work lives in `skills-local`.
- **Fleet-wide gate stalls opportunistic roll-up.** A gated client skips roll-up (3.2). If every active member is gated at once, pending `_inbox/` contributions are not rolled up until someone re-vendors to a new-enough client. Accepted tradeoff: protecting the vault from too-old clients takes precedence over roll-up latency, and the roll-up is idempotent so it simply happens once a current client next syncs.
- **Concurrent migration pushes.** Two clients may both apply and try to push the same migration; the transaction's fetch-rebase-retry catches up, and because the ops are idempotent the loser rebases onto an already-migrated tree and pushes an empty (dropped) commit or resets to the tip and finds the work done. Same convergence property as the roll-up transaction.

## 7. Relationship to existing artifacts

Implements master-design sections 3.6, 4.5, 4.9. Reuses `lib/gitsync.py` (`pull`, `push_paths`) and slots into the existing SessionStart hook between pull and roll-up. Completes the `CONTROL/skills/` distribution channel deferred in sub-project 2. Leaves TTL/freshness (sub-project 4) and the full installer/onboarding (sub-project 5) untouched.
