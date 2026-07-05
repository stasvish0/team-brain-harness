# TTL / freshness system (sub-project 4)

> Sub-project 4 of the group hive brain. Builds on sub-projects 1-3 and implements master-design section 4.7 ([2026-07-03-group-hive-brain-design.md](2026-07-03-group-hive-brain-design.md)). Ports the single-user EM OS memory-health subsystem (`last_verified` frontmatter, per-type horizons, a SessionStart health hook, and an on-demand audit) into the shared hive.

## 1. Context and goals

Shared knowledge ages. A decision recorded a year ago may no longer hold; a project note may be stale. Without a freshness signal, the assistant treats old notes as current fact. The single-user EM OS solved this with a `last_verified` date on each memory, per-type staleness horizons, a fast SessionStart warning, and a heavier on-demand audit. This sub-project ports that mechanism into the hive so group knowledge ages honestly, and adds deterministic near-duplicate detection.

**Goal:** every tracked note carries a `last_verified` date; each session start warns (fast, read-only) about notes past their horizon or hard expiry; an on-demand `/hive-audit` re-verifies stale notes (stamping the ones still true) and surfaces duplicates, committing shared stamps as a git transaction. All client-side, stdlib only, no server.

## 2. Non-goals and constraints

- **No LLM contradiction-hunting in this sub-project.** The single-user audit also hunts contradictions and writes `conflicts.json`; that judgment-heavy half is deferred. Only deterministic near-duplicate detection is in scope.
- **No new runtime dependency.** Stdlib only; in particular, no PyYAML (front-matter is parsed by a minimal scalar reader, see 4.2).
- **The session-start check is read-only and ephemeral.** Pure date math, no writes, no state file, recomputed each session (matching the single-user "pure date math" hook).
- **Stamping shared notes is a git write.** Bumping `last_verified` on a shared note is committed and pushed as a transaction (like the roll-up and migration transactions); stamps to `private/` stay local.
- **Opt-in.** A note is tracked only if it carries `last_verified` front-matter; untracked notes are ignored by the check.

## 3. Key decisions

### 3.1 Tracked notes: opt-in via front-matter
A tracked note is any markdown file with YAML front-matter carrying `last_verified: YYYY-MM-DD` (and an optional `review_by: YYYY-MM-DD` hard expiry). A note opts in by having the field; a shipped `knowledge-note.md` template carries it. Event records that use a JSON data block (meeting canonical notes from sub-project 2) are not front-matter notes and are out of scope.

### 3.2 Scope: freshness/TTL + deterministic duplicate detection
Build the freshness half fully (horizons, session warnings, re-verify + stamp) plus deterministic near-duplicate detection (normalized-content hash). Defer LLM contradiction-hunting and `conflicts.json`.

### 3.3 Architecture: deterministic lib + thin skill
`lib/freshness.py` owns the deterministic mechanics; a thin `/hive-audit` skill owns judgment (is a stale note still true?). The session-start check is read-only and client-local; stamping is a shared commit + push. Mirrors the sub-project 2/3 split.

### 3.4 Config: `CONTROL/health.json`, read directly
Per-type horizons, a default horizon, and the scan roots live in `CONTROL/health.json` (admin-owned, propagates via ordinary git pull). It is read live each session by the hook and the lib; it is pure data, not something "applied", so it needs no manifest version or `.applied.json` bookkeeping.

### 3.5 Per-session vs on-demand
The session-start hook does only fast, read-only date math (scan + warn). The heavier work (near-duplicate detection, re-verification judgment, stamping) lives only in the on-demand `/hive-audit`. A gated client (a `.control-block` present) skips the freshness check, because the hook already returns early on a control-plane block.

## 4. Architecture

### 4.1 New module: `lib/freshness.py`
- `read_health_config(repo) -> dict` — read `CONTROL/health.json`; if the file is absent, return a non-empty default: `default_horizon_days` 180, an empty per-type `horizons` map, and a default `scan_roots` list equal to the shared knowledge dirs plus `private` (`["org","product","engineering","design","customers","market","knowledge","projects","decisions","private"]`) so the check never silently does nothing.
- `parse_frontmatter(path) -> dict | None` — minimal scalar reader (see 4.2); returns the parsed scalar fields or None when there is no front-matter block.
- `note_status(frontmatter, today, config) -> str` — `"expired"` / `"stale"` / `"fresh"` (see 4.3). Returns None/`"untracked"` for a note without `last_verified`.
- `scan(repo, config, today) -> list[dict]` — walk each scan root, **silently skipping any root that does not exist** (shared roots exist in the hive; `private/` exists only on a client; a missing root is not an error), parse front-matter, classify; return `[{path, type, status, last_verified, age_days}]` for tracked notes only.
- `stamp(path, today) -> None` — rewrite the note's existing `last_verified:` line to `today` in place, atomically (temp + `os.replace`), preserving all other front-matter and body bytes. **Precondition:** `stamp` is only ever called on a note that `scan` returned, which by construction has a parseable `last_verified` line; if called on a note whose front-matter has no `last_verified` line, it raises (a precondition violation), never silently no-ops (a silent no-op would let the audit believe it stamped when it did not).
- `find_duplicates(repo, config) -> list[list[str]]` — clusters of tracked notes whose normalized body content hashes equal (near-duplicates).

All functions that depend on the current date take `today` as an explicit parameter, so tests are deterministic; the hook and skill pass `datetime.date.today()`.

### 4.2 Front-matter convention and the minimal parser
A tracked note:
```markdown
---
title: Adopt X for Y
type: decision
last_verified: 2026-07-05
review_by: 2026-12-31
---
# Adopt X for Y
body...
```
`type` selects the horizon; a missing/unknown type falls back to `default_horizon_days`. `review_by` is optional.

Because the harness is stdlib-only, `parse_frontmatter` does NOT use a YAML library. It: checks the file begins with a `---` line; reads lines until the closing `---`; parses each `key: value` line by splitting on the first `:`, stripping surrounding whitespace, surrounding quotes, and any trailing ` #` inline comment. It only needs the scalar fields `last_verified`, `review_by`, `type` (plus `title` for reporting). Nested/complex YAML is neither produced by the template nor required; a value it cannot parse as a scalar is simply ignored. `stamp` likewise operates line-wise on the `last_verified:` line, so it never needs to round-trip full YAML.

### 4.3 Status computation (pure date math)
Given `today` (a `date`) and a note's front-matter:
1. If `review_by` is present and `today > review_by` -> `"expired"` (hard override, highest priority). The boundary is exclusive: on `review_by` itself the note is not yet expired; it expires the day after (matching the strict-inequality staleness rule below).
2. Else if `last_verified` is present and `(today - last_verified).days > horizon` -> `"stale"`, where `horizon = config["horizons"].get(type, config["default_horizon_days"])`.
3. Else -> `"fresh"`.
A note without a parseable `last_verified` is untracked (excluded from `scan` output).

### 4.4 Session-start check (hook wiring)
`client-kit/.claude/hooks/sync_pull.py` calls `scan(repo, read_health_config(repo), date.today())` as the **final step of the non-blocked path, after `roll_up_all`**, and prints a concise summary plus one line per stale/expired note, for example:
```
freshness: 2 stale, 1 expired  (run /hive-audit to re-verify)
  STALE   engineering/adr-001.md  (verified 210d ago, horizon 180d)
  EXPIRED decisions/2026/q1-plan.md  (review_by 2026-06-01)
```
It is read-only, writes nothing, and persists no state (recomputed each session). It scans `private/` too (local read). **Placement requirement:** the freshness call MUST be after the `if cp["blocked"]: return` block, so a gated (too-old) client never reaches it and emits no freshness output. This is a required placement, not an emergent property.

### 4.5 The `/hive-audit` skill + deterministic helpers
Vendored via `client-kit/skills/hive-audit/SKILL.md` (so `instantiate` copies it into `CONTROL/skills/` and the sub-project-3 skills mirror delivers it to each client's `.claude/skills/`, exactly like `process-meeting`). On demand:
1. `scan` -> stale/expired notes.
2. For each, the assistant re-verifies against live/current knowledge. Still true -> `stamp(path, today)`. Not true -> escalate a rewrite or deletion to the human (never auto-deletes or rewrites shared knowledge).
3. `find_duplicates` -> near-duplicate clusters; the skill surfaces them and escalates merges to the human (auto-merging shared notes is destructive).
4. Commit + push the stamped **shared** notes as one transaction via `push_paths`, passing **only the concrete shared note paths it stamped** (never `private/...`, never `.applied.json`/`.control-block`). `push_paths` stages exactly those pathspecs and does not re-filter, so passing only shared note paths is the guarantee; gitignore is the backstop (`private/`, `.applied.json`, `.control-block` are all gitignored, so a stray path would stage nothing). Stamps to `private/` notes are edited in place and never pushed (gitignored).

**Push-conflict handling:** `push_paths` raises `RuntimeError` on a real rebase conflict. The audit does NOT swallow it: it surfaces the failure to the user (the stamp did not land; retry the audit) and leaves the repo clean the way `push_paths` does (it aborts its own rebase). Any `private/` stamps already written locally simply remain; re-running the audit re-stamps idempotently (a stamp to the same `today` is an empty diff), so a failed shared push never corrupts state or double-counts.

### 4.6 Config and template files (in `hive-template/`)
- `CONTROL/health.json` seeded with `default_horizon_days`, a `horizons` map (e.g. reference 180, project 30, decision 365, knowledge 180), and a `scan_roots` list (the shared knowledge dirs plus `private`).
- `templates/knowledge-note.md` carrying the front-matter convention, so members create tracked notes correctly.

## 5. Testing

- **Unit:** `parse_frontmatter` (scalar values, quotes, inline comments, missing block, note without `last_verified`); `note_status` (fresh / stale / expired, the horizon boundary, and `review_by` precedence over horizon); `scan` classification across multiple roots and skipping untracked files; `stamp` updates only `last_verified` and preserves all other bytes; `find_duplicates` clusters identical and near-identical notes and separates distinct ones; `read_health_config` default when the file is missing.
- **Integration** (temp git repos): the hook prints stale/expired warnings for a seeded old note with an injected `today`; stamping a shared note commits + pushes exactly that path and it reaches a fresh clone; a `private/` note stamp is not pushed; a gated client (a `.control-block` present) skips the freshness check and emits no freshness output.
- **End-to-end:** a note aged past its horizon shows STALE at a client's session start; after a `stamp` + push (the audit's mechanical step), a second client's session-start check sees it fresh.

## 6. Open questions and risks

- **Minimal front-matter parser vs real YAML.** The scalar reader handles the template's simple `key: value` fields but not arbitrary YAML. Acceptable because tracked notes follow the shipped template; a malformed front-matter value is ignored rather than crashing the session. If richer front-matter is ever needed, a parser upgrade is localized to `parse_frontmatter`/`stamp`.
- **Duplicate detection is exact/near-exact only.** Content-hash clustering catches copies and trivial edits, not semantically-equivalent rewrites (that is contradiction/semantic work, deferred with the LLM half).
- **Clock skew / timezones.** Status is computed from `date.today()` on the client; day-granularity horizons make timezone differences immaterial.
- **Stamping churn.** An audit that re-confirms many notes produces one commit touching several files; concurrent audits converge through `push_paths`'s fetch-rebase-retry, and a stamp is idempotent (re-stamping to the same `today` is a no-op diff).

## 7. Relationship to existing artifacts

Implements master-design 4.7. Reuses the sub-project-3 skills-distribution channel (`CONTROL/skills/`) and `CONTROL/` config ownership, and `lib/gitsync.py` `push_paths` for the stamp transaction. Slots a read-only check into the existing SessionStart hook after the control plane. Leaves the full installer / onboarding (sub-project 5) as the only remaining piece.
