# Meeting Roll-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic meeting roll-up (a shared `lib/meeting_rollup.py`, a shared push helper, session-start wiring, and a thin `/process-meeting` skill) so several attendees' contributions merge into one canonical note, idempotently, with raw transcripts staying private.

**Architecture:** All code runs client-side (no server/CI). A member's `/process-meeting` skill summarizes a private raw transcript into a structured JSON contribution written to a shared, ephemeral, author-namespaced inbox (`meetings/<id>/_inbox/<author-id>.md`) and publishes it. On any member's next session-start, the pull hook rolls up each meeting's inbox into a single canonical note (`meetings/<id>/<slug>.md`) as a per-meeting transaction: merge new-hash contributions, delete folded inbox files, commit only that meeting dir, push with fetch-rebase-retry, and on failure `git reset --hard` to the remote tip (which restores the inbox for a later retry). The canonical note carries a machine-readable fenced JSON block (stdlib `json.dumps(sort_keys=True, ensure_ascii=False, indent=2)`) as its source of truth plus a rendered Markdown body.

**Tech Stack:** Python 3.11+ (stdlib only: `json`, `hashlib`, `re`, `pathlib`, `subprocess`), pytest, git via the existing `lib/gitsync.py` helpers. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-07-04-meeting-rollup-design.md`. Read it before starting; this plan implements sections 4 and 5.

**Branch:** work on `sp2-meeting-rollup` (already checked out). Land via PR at the end (main is branch-protected).

**Test command (from repo root):** `./.venv/bin/python -m pytest -q` (the venv already has pytest; `pyproject.toml` sets `pythonpath = ["."]`, so `lib`/`tools` import with no install).

---

## File Structure

**Create:**
- `lib/meeting_rollup.py` — the deterministic core. One responsibility: turn inbox contributions + an existing canonical note into a merged canonical note, and drive the per-meeting roll-up transaction. Pure functions (`slugify`, `normalize`, `content_hash`, `parse_payload`, `merge`, `render`, `find_meeting_dirs`) plus one repo-touching `roll_up(repo, meeting_dir)`.
- `tests/test_meeting_rollup_unit.py` — unit tests for the pure functions.
- `tests/test_meeting_rollup_integration.py` — `roll_up()` against a temp git repo.
- `tests/test_rollup_e2e.py` — two contributors + a third client's session-start roll-up, end to end.
- `client-kit/.claude/skills/process-meeting/SKILL.md` — the thin skill. Placed under `client-kit/.claude/` so `setup_client.py` (which copies `client-kit/.claude/` wholesale into each client) delivers it to every member immediately, exactly like the hooks. It lands local-only in the clone (the client's `.git/info/exclude` ignores `/.claude/`), which is correct: a skill is client tooling, not shared hive content. NOTE: the canonical shared-skills home (`client-kit/skills/` -> hive `CONTROL/skills/`) and its control-plane distribution to clients is a sub-project-3 concern; this direct placement is the working delivery path for now.

**Modify:**
- `lib/gitsync.py` — extract the fetch-rebase-retry push loop from `publish` into a reusable `push_paths(repo, message, paths, remote, branch, max_retries)` that stages a directory pathspec set (capturing deletions) and pushes; `publish` keeps its allowlist behavior by delegating to it. Add nothing to `pull`.
- `client-kit/.claude/hooks/sync_pull.py` — after `pull`, call a new `roll_up_all(repo)` step.
- `hive-template/meetings/.gitkeep` — already exists; no change, but roll-up writes under `meetings/`.

**Do NOT touch:** `publish_allowlist.txt` (`meetings/` is already allowlisted, line 11), the privacy/gitignore machinery, or `setup_client.py` (it already vendors `.claude/` + `lib/`, so the new hook step and library ship to clients automatically).

---

## Conventions to follow (from the existing codebase)

- Tests use real git against `tmp_path`. Reuse the `bare_remote` fixture in `tests/conftest.py` and its `init_identity(repo)` / `_git(repo, *args)` helpers. For end-to-end, follow `tests/test_e2e_loop.py` (uses `instantiate`, `setup_client`, `pull`, and `_bare_from`).
- Import the code under test as `from lib.meeting_rollup import ...` and `from lib.gitsync import ...` (pythonpath is the repo root).
- Keep functions small and stdlib-only. No new dependencies.
- Commit after each task with a `feat:`/`refactor:`/`test:` message; end every commit message with:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```

---

## Task 1: `slugify` and `normalize`

**Files:**
- Create: `lib/meeting_rollup.py`
- Test: `tests/test_meeting_rollup_unit.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_meeting_rollup_unit.py
from lib.meeting_rollup import slugify, normalize

def test_slugify_lowercases_and_hyphenates():
    assert slugify("Daily Standup") == "daily-standup"

def test_slugify_strips_punctuation_and_collapses():
    assert slugify("  Weekly  Sync!! (Eng) ") == "weekly-sync-eng"

def test_slugify_unicode_is_dropped_to_ascii_words():
    # non-ascii word chars are dropped; result stays url/file safe
    assert slugify("Café review") == "caf-review"

def test_normalize_lowercases_collapses_ws_and_strips_trailing_punct():
    assert normalize("  Ship  v2  behind a flag. ") == "ship v2 behind a flag"
    assert normalize("Wire the feature flag!!!") == "wire the feature flag"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -q`
Expected: FAIL with `ModuleNotFoundError` / `ImportError: cannot import name 'slugify'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# lib/meeting_rollup.py
"""Deterministic meeting roll-up: merge author-namespaced inbox contributions
into one canonical note per meeting. Stdlib only. See
docs/superpowers/specs/2026-07-04-meeting-rollup-design.md."""
import re

def slugify(title):
    """Lowercase, keep word chars, collapse the rest to single hyphens."""
    s = re.sub(r"[^a-z0-9]+", "-", title.lower())
    return s.strip("-")

def normalize(text):
    """Dedupe key for free text: lowercase, collapse whitespace, strip
    trailing punctuation."""
    s = re.sub(r"\s+", " ", text.strip().lower())
    return s.rstrip(".!?,;: ").strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add lib/meeting_rollup.py tests/test_meeting_rollup_unit.py
git commit -m "feat: slugify + normalize helpers for meeting roll-up

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `content_hash` (stable over canonicalized payload)

**Files:**
- Modify: `lib/meeting_rollup.py`
- Test: `tests/test_meeting_rollup_unit.py`

**Context:** `content_hash` must be stable across machines and independent of key ordering, `by` attribution, and volatile metadata (`title`/`date`/`author`). It hashes only the normalized `decisions`/`action_items`/`notes`. Two authors who summarized identically must hash identically.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_meeting_rollup_unit.py
from lib.meeting_rollup import content_hash

def _payload(**over):
    base = {
        "meeting_id": "2026-07-04-standup", "title": "Daily Standup",
        "date": "2026-07-04", "author": "alice",
        "decisions": ["Ship v2 behind a flag"],
        "action_items": [{"owner": "bob", "text": "Wire the feature flag"}],
        "notes": ["Discussed staging capacity"],
    }
    base.update(over)
    return base

def test_content_hash_ignores_volatile_metadata_and_author():
    a = _payload(author="alice", title="Daily Standup", date="2026-07-04")
    b = _payload(author="bob", title="DAILY STANDUP", date="2026-07-05")
    assert content_hash(a) == content_hash(b)

def test_content_hash_ignores_by_attribution():
    a = _payload()
    b = _payload(decisions=["Ship v2 behind a flag"])
    b_with_by = dict(b, decisions=[{"text": "Ship v2 behind a flag", "by": ["x"]}])
    # payloads may carry either bare strings or {text,...}; hash normalizes both
    assert content_hash(a) == content_hash(b_with_by)

def test_content_hash_changes_when_a_decision_changes():
    a = _payload()
    b = _payload(decisions=["Ship v2 behind a feature flag"])
    assert content_hash(a) != content_hash(b)

def test_content_hash_is_order_independent():
    a = _payload(notes=["one", "two"])
    b = _payload(notes=["two", "one"])
    assert content_hash(a) == content_hash(b)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -k content_hash -q`
Expected: FAIL with `ImportError: cannot import name 'content_hash'`.

- [ ] **Step 3: Write the minimal implementation**

Add helpers that read both the "bare" contribution shape (`decisions: [str]`, `action_items: [{owner,text}]`, `notes: [str]`) and the "canonical" item shape (`{text, by}`), reducing each to its normalized comparable core.

```python
# add to lib/meeting_rollup.py
import hashlib, json

def _decision_text(d):
    return d if isinstance(d, str) else d["text"]

def _note_text(n):
    return n if isinstance(n, str) else n["text"]

def _canonical_core(payload):
    """The hashable/comparable core: normalized text only, sorted, no
    attribution, no metadata."""
    decisions = sorted(normalize(_decision_text(d)) for d in payload.get("decisions", []))
    actions = sorted(
        (normalize(a["owner"]), normalize(a["text"]))
        for a in payload.get("action_items", [])
    )
    notes = sorted(normalize(_note_text(n)) for n in payload.get("notes", []))
    return {"decisions": decisions, "action_items": actions, "notes": notes}

def content_hash(payload):
    core = _canonical_core(payload)
    blob = json.dumps(core, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -k content_hash -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add lib/meeting_rollup.py tests/test_meeting_rollup_unit.py
git commit -m "feat: stable content_hash over canonicalized meeting payload

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `merge` (deterministic, additive, ledger-guarded)

**Files:**
- Modify: `lib/meeting_rollup.py`
- Test: `tests/test_meeting_rollup_unit.py`

**Context:** `merge(existing, contributions)` returns a new canonical payload dict. Rules (spec 5.2): skip any contribution whose `content_hash` is already in `existing["merged_authors"]`; fold the rest. Union decisions/notes deduped by `normalize(text)`; dedupe action_items by `(normalize(owner), normalize(text))`; union `by` attribution (the contribution's `author`); append `{author, content_hash}` to `merged_authors`. Canonical items are stored as `{text, by:[...]}` (decisions/notes) and `{owner, text, by:[...]}` (action_items). `existing` may be None (first roll-up).

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_meeting_rollup_unit.py
from lib.meeting_rollup import merge, content_hash

def _contrib(author, decisions=None, action_items=None, notes=None):
    return {
        "meeting_id": "2026-07-04-standup", "title": "Daily Standup",
        "date": "2026-07-04", "author": author,
        "decisions": decisions or [], "action_items": action_items or [],
        "notes": notes or [],
    }

def test_merge_two_authors_unions_and_attributes():
    a = _contrib("alice", decisions=["Ship v2 behind a flag"],
                 action_items=[{"owner": "bob", "text": "Wire the feature flag"}])
    b = _contrib("bob", decisions=["Ship v2 behind a flag"],
                 notes=["Staging is tight"])
    out = merge(None, [a, b])
    # decision deduped by normalized text, attribution unions both authors
    assert out["decisions"] == [{"text": "Ship v2 behind a flag", "by": ["alice", "bob"]}]
    assert out["action_items"] == [
        {"owner": "bob", "text": "Wire the feature flag", "by": ["alice"]}]
    assert out["notes"] == [{"text": "Staging is tight", "by": ["bob"]}]
    assert {e["author"] for e in out["merged_authors"]} == {"alice", "bob"}
    assert out["meeting_id"] == "2026-07-04-standup"

def test_merge_is_idempotent_on_already_folded_contribution():
    a = _contrib("alice", decisions=["Ship v2 behind a flag"])
    once = merge(None, [a])
    twice = merge(once, [a])  # same content_hash already in ledger -> skipped
    assert twice == once

def test_merge_late_new_author_folds_into_existing():
    a = _contrib("alice", decisions=["Ship it"])
    first = merge(None, [a])
    c = _contrib("carol", decisions=["Ship it"], notes=["QA signed off"])
    second = merge(first, [c])
    assert second["decisions"] == [{"text": "Ship it", "by": ["alice", "carol"]}]
    assert second["notes"] == [{"text": "QA signed off", "by": ["carol"]}]
    assert len(second["merged_authors"]) == 2

def test_merge_same_author_rerun_adds_new_distinct_items():
    a = _contrib("alice", decisions=["Ship it"])
    first = merge(None, [a])
    a2 = _contrib("alice", decisions=["Ship it", "Also update docs"])
    second = merge(first, [a2])
    texts = sorted(d["text"] for d in second["decisions"])
    assert texts == ["Also update docs", "Ship it"]
    # additive: the earlier "Ship it" is not retracted; two ledger entries for alice
    assert sum(1 for e in second["merged_authors"] if e["author"] == "alice") == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -k merge -q`
Expected: FAIL with `ImportError: cannot import name 'merge'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# add to lib/meeting_rollup.py

def _empty_canonical(meta):
    return {
        "meeting_id": meta.get("meeting_id"),
        "title": meta.get("title"),
        "date": meta.get("date"),
        "merged_authors": [],
        "decisions": [],
        "action_items": [],
        "notes": [],
    }

def _fold_text_items(existing_items, incoming_texts, author, key=normalize):
    """existing_items: list of {text, by}. incoming_texts: list[str]."""
    index = {key(it["text"]): it for it in existing_items}
    for text in incoming_texts:
        it = index.get(key(text))
        if it is None:
            it = {"text": text, "by": []}
            existing_items.append(it)
            index[key(text)] = it
        if author not in it["by"]:
            it["by"].append(author)

def _fold_actions(existing_actions, incoming, author):
    index = {(normalize(a["owner"]), normalize(a["text"])): a for a in existing_actions}
    for a in incoming:
        k = (normalize(a["owner"]), normalize(a["text"]))
        it = index.get(k)
        if it is None:
            it = {"owner": a["owner"], "text": a["text"], "by": []}
            existing_actions.append(it)
            index[k] = it
        if author not in it["by"]:
            it["by"].append(author)

def merge(existing, contributions):
    canonical = existing if existing is not None else None
    known = set()
    if canonical is not None:
        known = {e["content_hash"] for e in canonical.get("merged_authors", [])}
    for c in contributions:
        h = content_hash(c)
        if h in known:
            continue
        if canonical is None:
            canonical = _empty_canonical(c)
        author = c["author"]
        _fold_text_items(canonical["decisions"],
                         [_decision_text(d) for d in c.get("decisions", [])], author)
        _fold_actions(canonical["action_items"], c.get("action_items", []), author)
        _fold_text_items(canonical["notes"],
                         [_note_text(n) for n in c.get("notes", [])], author)
        canonical["merged_authors"].append({"author": author, "content_hash": h})
        known.add(h)
    return canonical if canonical is not None else _empty_canonical({})
```

Note: `by` lists accumulate in insertion order here; Task 4's `render`/ordering imposes the total sort for output. The `merge` output dict is compared in tests only via fields whose order is deterministic given the inputs; the idempotency test relies on the ledger skip, so re-merging the identical contribution returns the unchanged dict.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -k merge -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add lib/meeting_rollup.py tests/test_meeting_rollup_unit.py
git commit -m "feat: deterministic ledger-guarded meeting merge

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `render` + `parse_payload` (pinned serializer, byte-identical, round-trip)

**Files:**
- Modify: `lib/meeting_rollup.py`
- Test: `tests/test_meeting_rollup_unit.py`

**Context:** `render(canonical)` produces the full canonical-note file text: a rendered Markdown body followed by the sentinel `<!-- team-brain-harness:rollup-data -->` and a fenced ```json block emitted with `json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2)` + trailing newline. Before serializing, `render` imposes the total ordering (spec 5.2): decisions/notes sorted by `normalize(text)`, action_items grouped by owner then `normalize(text)`, `by` sorted by author-id, `merged_authors` sorted by `(author, content_hash)`. `parse_payload(path)` finds the sentinel + fenced JSON and returns the dict (or None). The pair must round-trip and be byte-identical across independent renders.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_meeting_rollup_unit.py
from lib.meeting_rollup import render, parse_payload, merge, SENTINEL

def test_render_is_byte_identical_regardless_of_processing_order(tmp_path):
    # two DISTINCT-content contributions (distinct content_hash) so both fold in
    # both orders; the total ordering in render makes the output byte-identical.
    a = _contrib("alice", decisions=["B decision"], notes=["z note"])
    b = _contrib("bob", decisions=["A decision"], notes=["a note"])
    p1 = merge(None, [a, b])
    p2 = merge(None, [b, a])  # different processing order
    assert render(p1) == render(p2)

def test_render_body_has_sections_and_sorted_items():
    p = merge(None, [_contrib("alice", decisions=["B", "A"])])
    text = render(p)
    body = text.split(SENTINEL)[0]
    assert "## Decisions" in body
    # sorted by normalized text -> A before B
    assert body.index("- A") < body.index("- B")

def test_render_then_parse_roundtrips(tmp_path):
    p = merge(None, [_contrib("alice", decisions=["Ship it"],
                              action_items=[{"owner": "bob", "text": "do X"}],
                              notes=["a note"])])
    f = tmp_path / "note.md"
    f.write_text(render(p))
    loaded = parse_payload(f)
    assert loaded["decisions"] == [{"text": "Ship it", "by": ["alice"]}]
    assert loaded["action_items"] == [{"owner": "bob", "text": "do X", "by": ["alice"]}]
    assert content_hash(loaded) == content_hash(p)

def test_parse_payload_returns_none_without_block(tmp_path):
    f = tmp_path / "plain.md"
    f.write_text("# Just prose\nno data here\n")
    assert parse_payload(f) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -k "render or parse" -q`
Expected: FAIL with `ImportError` (`render` / `parse_payload` / `SENTINEL` not defined).

- [ ] **Step 3: Write the minimal implementation**

```python
# add to lib/meeting_rollup.py
SENTINEL = "<!-- team-brain-harness:rollup-data -->"

def _ordered(canonical):
    """Return a new payload dict with every list in canonical total order."""
    decisions = sorted(canonical.get("decisions", []), key=lambda d: normalize(d["text"]))
    actions = sorted(canonical.get("action_items", []),
                     key=lambda a: (a["owner"], normalize(a["text"])))
    notes = sorted(canonical.get("notes", []), key=lambda n: normalize(n["text"]))
    def _by(items):
        for it in items:
            it["by"] = sorted(it["by"])
        return items
    ledger = sorted(canonical.get("merged_authors", []),
                    key=lambda e: (e["author"], e["content_hash"]))
    return {
        "meeting_id": canonical.get("meeting_id"),
        "title": canonical.get("title"),
        "date": canonical.get("date"),
        "merged_authors": ledger,
        "decisions": _by(decisions),
        "action_items": _by(actions),
        "notes": _by(notes),
    }

def _render_body(p):
    lines = [f"# {p.get('title') or p.get('meeting_id')} - {p.get('date') or ''}".rstrip(), ""]
    lines += ["## Decisions"]
    lines += [f"- {d['text']}" for d in p["decisions"]] or ["- (none)"]
    lines += ["", "## Action items"]
    owners = []
    for a in p["action_items"]:
        if a["owner"] not in owners:
            owners.append(a["owner"])
    if not owners:
        lines += ["- (none)"]
    for owner in owners:
        lines += [f"### {owner}"]
        lines += [f"- {a['text']}" for a in p["action_items"] if a["owner"] == owner]
    lines += ["", "## Notes"]
    lines += [f"- {n['text']}" for n in p["notes"]] or ["- (none)"]
    return "\n".join(lines).rstrip() + "\n"

def render(canonical):
    p = _ordered(canonical)
    body = _render_body(p)
    block = json.dumps(p, sort_keys=True, ensure_ascii=False, indent=2)
    return f"{body}\n{SENTINEL}\n```json\n{block}\n```\n"

def parse_payload(path):
    text = __import__("pathlib").Path(path).read_text()
    if SENTINEL not in text:
        return None
    after = text.split(SENTINEL, 1)[1]
    m = re.search(r"```json\n(.*?)\n```", after, re.DOTALL)
    if not m:
        return None
    return json.loads(m.group(1))
```

(Prefer a top-level `from pathlib import Path` import instead of `__import__`; use `Path(path).read_text()`. Add `from pathlib import Path` at the top of the module.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -q`
Expected: PASS (all unit tests green).

- [ ] **Step 5: Commit**

```bash
git add lib/meeting_rollup.py tests/test_meeting_rollup_unit.py
git commit -m "feat: pinned JSON-block render + parse for canonical notes

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `find_meeting_dirs`

**Files:**
- Modify: `lib/meeting_rollup.py`
- Test: `tests/test_meeting_rollup_unit.py`

**Context:** The skill uses this to discover existing meeting dirs for a date (discover-or-create, spec 4.2). A meeting dir is `meetings/<YYYY-MM-DD>-<slug>/`. Return the matching dir Paths under `<repo>/meetings/` whose name starts with the date, sorted.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_meeting_rollup_unit.py
from lib.meeting_rollup import find_meeting_dirs

def test_find_meeting_dirs_matches_date_prefix(tmp_path):
    meetings = tmp_path / "meetings"
    (meetings / "2026-07-04-standup").mkdir(parents=True)
    (meetings / "2026-07-04-retro").mkdir()
    (meetings / "2026-07-05-planning").mkdir()
    got = sorted(p.name for p in find_meeting_dirs(tmp_path, "2026-07-04"))
    assert got == ["2026-07-04-retro", "2026-07-04-standup"]

def test_find_meeting_dirs_empty_when_no_meetings_dir(tmp_path):
    assert find_meeting_dirs(tmp_path, "2026-07-04") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -k find_meeting -q`
Expected: FAIL with `ImportError: cannot import name 'find_meeting_dirs'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# add to lib/meeting_rollup.py
def find_meeting_dirs(repo, date):
    base = Path(repo) / "meetings"
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir()
                  if p.is_dir() and p.name.startswith(date + "-"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_unit.py -k find_meeting -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add lib/meeting_rollup.py tests/test_meeting_rollup_unit.py
git commit -m "feat: find_meeting_dirs for discover-or-create meeting ids

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Extract `push_paths` in `lib/gitsync.py`; delegate `publish` to it

**Files:**
- Modify: `lib/gitsync.py:27-45` (the `publish` function)
- Test: `tests/test_meeting_rollup_integration.py` (new), plus existing `tests/test_publish_concurrent.py` and `tests/test_conflict_handling.py` must still pass unchanged.

**Context:** Roll-up needs the same fetch-rebase-retry push loop but stages an explicit set of directory pathspecs (to capture inbox deletions), not the allowlist. Extract the loop into `push_paths(repo, message, paths, remote="origin", branch="main", max_retries=5)` and have `publish` delegate. Behavior of `publish` must be unchanged (existing tests are the guard). `push_paths` stages each path with `git add -- <path>` (directory pathspec captures adds/mods/deletes), returns `"nothing-to-publish"` when nothing staged, else runs the commit + push/fetch/rebase/retry loop, raising `RuntimeError` on conflict or exhausted retries exactly as today.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_meeting_rollup_integration.py
import subprocess
from pathlib import Path
from lib.gitsync import run_git, push_paths
from tests.conftest import init_identity  # reuse identity helper

def _clone(remote, dest):
    subprocess.run(["git", "clone", str(remote), str(dest)], check=True)
    init_identity(dest)
    return dest

def test_push_paths_stages_including_deletions(bare_remote, tmp_path):
    a = _clone(bare_remote, tmp_path / "a")
    mdir = a / "meetings" / "2026-07-04-standup"
    (mdir / "_inbox").mkdir(parents=True)
    (mdir / "_inbox" / "alice.md").write_text("x\n")
    assert push_paths(a, "add inbox", ["meetings/"]) == "pushed"

    # now delete the inbox file and add a canonical note; push via directory pathspec
    (mdir / "_inbox" / "alice.md").unlink()
    (mdir / "standup.md").write_text("canonical\n")
    assert push_paths(a, "roll up", ["meetings/"]) == "pushed"

    # a fresh clone must NOT contain the deleted inbox file
    b = _clone(bare_remote, tmp_path / "b")
    assert (b / "meetings" / "2026-07-04-standup" / "standup.md").exists()
    assert not (b / "meetings" / "2026-07-04-standup" / "_inbox" / "alice.md").exists()

def test_push_paths_nothing_to_publish(bare_remote, tmp_path):
    a = _clone(bare_remote, tmp_path / "a")
    assert push_paths(a, "noop", ["meetings/"]) == "nothing-to-publish"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_integration.py -q`
Expected: FAIL with `ImportError: cannot import name 'push_paths'`.

- [ ] **Step 3: Refactor `publish` and add `push_paths`**

Replace `lib/gitsync.py:27-45` with:

```python
def push_paths(repo, message, paths, remote="origin", branch="main", max_retries=5):
    """Stage the given pathspecs (directory pathspecs also capture deletions),
    commit if anything is staged, then push with fetch->rebase->retry so a
    concurrent push is caught up to, never clobbered. Raises on a real conflict."""
    for p in paths:
        run_git(repo, "add", "--", p, check=False)
    staged = run_git(repo, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return "nothing-to-publish"
    run_git(repo, "commit", "-m", message)
    for _ in range(max_retries):
        push = run_git(repo, "push", remote, branch, check=False)
        if push.returncode == 0:
            return "pushed"
        run_git(repo, "fetch", remote, branch)
        rebase = run_git(repo, "rebase", f"{remote}/{branch}", check=False)
        if rebase.returncode != 0:
            run_git(repo, "rebase", "--abort", check=False)
            raise RuntimeError("push_paths: rebase conflict on a shared file; needs manual resolution")
    raise RuntimeError("push_paths: push failed after retries")

def publish(repo, message, allow_paths, remote="origin", branch="main", max_retries=5):
    """Publish allowlisted shared paths. Thin wrapper over push_paths so the
    allowlist stays the single source of truth for what a member may share."""
    return push_paths(repo, message, allow_paths, remote=remote, branch=branch,
                      max_retries=max_retries)
```

Keep `stage_allowlist` in the module (it is still imported/tested by `tests/test_stage_allowlist.py`); `publish` no longer needs to call it since `push_paths` stages inline, but do not delete it.

- [ ] **Step 4: Run the full suite to verify nothing regressed**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS, including `test_publish_concurrent.py`, `test_conflict_handling.py`, `test_stage_allowlist.py`, and the new integration tests.

- [ ] **Step 5: Commit**

```bash
git add lib/gitsync.py tests/test_meeting_rollup_integration.py
git commit -m "refactor: extract push_paths from publish (stages deletions for roll-up)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: `roll_up(repo, meeting_dir)` (the per-meeting transaction core)

**Files:**
- Modify: `lib/meeting_rollup.py`
- Test: `tests/test_meeting_rollup_integration.py`

**Context:** `roll_up(repo, meeting_dir)` performs the filesystem side of one meeting's roll-up (no git). It: scans `meeting_dir/_inbox/*.md`; if none, returns False. Parses each contribution payload; loads the existing canonical note payload if present (the single `*.md` in `meeting_dir` that is not under `_inbox/`); computes which contributions are new-hash; if none are new, returns False and touches nothing. Otherwise `merge`s, writes the canonical note (filename `<slug>.md` where slug is derived from the meeting dir name, e.g. dir `2026-07-04-standup` -> `standup.md`; if a canonical file already exists reuse its name), deletes the folded inbox files, and returns True. The git commit/push is the hook's job (Task 8), keeping `roll_up` pure-ish and unit-testable without a remote.

**Canonical filename rule:** derive from the meeting dir name by stripping the leading `YYYY-MM-DD-` date prefix; e.g. `2026-07-04-standup` -> `standup.md`. If the dir name is only a date (no slug), use `meeting.md`. If a non-`_inbox` `*.md` already exists, reuse it.

- [ ] **Step 1: Write the failing tests**

```python
# add to tests/test_meeting_rollup_integration.py
from lib.meeting_rollup import roll_up, render, parse_payload, merge

def _write_contrib(mdir, author, payload_text):
    inbox = mdir / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    from lib.meeting_rollup import SENTINEL
    import json as _json
    (inbox / f"{author}.md").write_text(
        f"{SENTINEL}\n```json\n{_json.dumps(payload_text)}\n```\n")

def _contrib_payload(author, decisions=None, notes=None):
    return {"meeting_id": "2026-07-04-standup", "title": "Daily Standup",
            "date": "2026-07-04", "author": author,
            "decisions": decisions or [], "action_items": [], "notes": notes or []}

def test_roll_up_merges_two_and_deletes_inbox(tmp_path):
    mdir = tmp_path / "meetings" / "2026-07-04-standup"
    _write_contrib(mdir, "alice", _contrib_payload("alice", decisions=["Ship it"]))
    _write_contrib(mdir, "bob", _contrib_payload("bob", notes=["Staging tight"]))
    changed = roll_up(tmp_path, mdir)
    assert changed is True
    canon = mdir / "standup.md"
    assert canon.exists()
    p = parse_payload(canon)
    assert p["decisions"] == [{"text": "Ship it", "by": ["alice"]}]
    assert p["notes"] == [{"text": "Staging tight", "by": ["bob"]}]
    assert not (mdir / "_inbox" / "alice.md").exists()
    assert not (mdir / "_inbox" / "bob.md").exists()

def test_roll_up_noop_when_no_inbox(tmp_path):
    mdir = tmp_path / "meetings" / "2026-07-04-standup"
    mdir.mkdir(parents=True)
    assert roll_up(tmp_path, mdir) is False

def test_roll_up_late_contribution_folds_and_is_idempotent(tmp_path):
    mdir = tmp_path / "meetings" / "2026-07-04-standup"
    _write_contrib(mdir, "alice", _contrib_payload("alice", decisions=["Ship it"]))
    assert roll_up(tmp_path, mdir) is True
    # late: carol contributes after the first roll-up
    _write_contrib(mdir, "carol", _contrib_payload("carol", notes=["QA ok"]))
    assert roll_up(tmp_path, mdir) is True
    p = parse_payload(mdir / "standup.md")
    assert p["notes"] == [{"text": "QA ok", "by": ["carol"]}]
    assert len(p["merged_authors"]) == 2
    # idempotent: no inbox left -> no-op
    assert roll_up(tmp_path, mdir) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_integration.py -k roll_up -q`
Expected: FAIL with `ImportError: cannot import name 'roll_up'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# add to lib/meeting_rollup.py
def _canonical_path(meeting_dir):
    """Deterministic canonical-note path: prefer the slug derived from the dir
    name; if that file exists reuse it; else if some other top-level .md exists
    (a stray) use the sorted-first; else the derived path."""
    meeting_dir = Path(meeting_dir)
    name = meeting_dir.name
    slug = name[len("YYYY-MM-DD-"):] if len(name) > 11 and name[10] == "-" else ""
    derived = meeting_dir / (f"{slug}.md" if slug else "meeting.md")
    if derived.exists():
        return derived
    existing = sorted(meeting_dir.glob("*.md"))  # non-recursive: excludes _inbox/
    return existing[0] if existing else derived

def roll_up(repo, meeting_dir):
    meeting_dir = Path(meeting_dir)
    inbox = meeting_dir / "_inbox"
    contrib_files = sorted(inbox.glob("*.md")) if inbox.is_dir() else []
    # parse once, keep (file, payload) pairs aligned; drop unparseable files
    pairs = [(f, parse_payload(f)) for f in contrib_files]
    pairs = [(f, c) for f, c in pairs if c is not None]
    if not pairs:
        return False
    canon_path = _canonical_path(meeting_dir)
    existing = parse_payload(canon_path) if canon_path.exists() else None
    known = set(e["content_hash"] for e in (existing or {}).get("merged_authors", []))
    new = [c for _, c in pairs if content_hash(c) not in known]
    if not new:
        return False  # nothing new -> touch nothing, worktree stays clean
    merged = merge(existing, new)
    canon_path.write_text(render(merged))
    # every parsed contribution is now reflected in canonical (folded or already
    # known), so delete them all; unparseable files (excluded above) are left alone
    for f, _ in pairs:
        f.unlink()
    try:
        inbox.rmdir()  # drop the now-empty inbox dir; harmless if not empty
    except OSError:
        pass
    return True
```

Note: the delete uses the already-parsed `pairs` (no second re-parse). We only reach the delete when `new` is non-empty, so cleanup always happens inside a real (to-be-committed) transaction, never as an uncommitted no-op.

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_integration.py -k roll_up -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add lib/meeting_rollup.py tests/test_meeting_rollup_integration.py
git commit -m "feat: roll_up per-meeting merge (write canonical, delete folded inbox)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: `roll_up_all(repo)` transaction driver + hook wiring

**Files:**
- Modify: `lib/meeting_rollup.py` (add `roll_up_all`)
- Modify: `client-kit/.claude/hooks/sync_pull.py`
- Test: `tests/test_meeting_rollup_integration.py`

**Context:** `roll_up_all(repo, remote="origin", branch="main")` is the transaction driver called by the hook after `pull`. For each `meetings/*/` that has `_inbox/*.md`, run the per-meeting transaction: `roll_up` (filesystem), and if it changed, `push_paths(repo, msg, [meeting_dir_relpath])`; on any `RuntimeError` from the push, `run_git(repo, "reset", "--hard", f"{remote}/{branch}")` to restore the pre-transaction state (including the inbox files, which exist at the remote tip per the spec invariant) and continue to the next meeting. Returns a list of `(meeting_dir_name, status)` for the caller to report. The worktree is left clean between meetings.

The hook change: after `print(pull(a.repo))`, call `roll_up_all(a.repo)` and print a one-line summary per rolled-up meeting.

- [ ] **Step 1: Write the failing test**

```python
# add to tests/test_meeting_rollup_integration.py
from lib.meeting_rollup import roll_up_all

def test_roll_up_all_pushes_canonical_and_clears_inbox(bare_remote, tmp_path):
    # a client with two published inbox contributions to the same meeting
    a = _clone(bare_remote, tmp_path / "a")
    mdir = a / "meetings" / "2026-07-04-standup"
    _write_contrib(mdir, "alice", _contrib_payload("alice", decisions=["Ship it"]))
    _write_contrib(mdir, "bob", _contrib_payload("bob", notes=["Staging tight"]))
    push_paths(a, "inbox", ["meetings/"])  # contributions are at the remote tip

    # a second client pulls (mirrors the hook: pull THEN roll up) and rolls up
    from lib.gitsync import pull
    b = _clone(bare_remote, tmp_path / "b")
    pull(b)  # exercises the fetch-before-rollup contract the reset invariant relies on
    results = roll_up_all(b)
    assert ("2026-07-04-standup", "pushed") in results

    # canonical landed on the remote; inbox is gone
    c = _clone(bare_remote, tmp_path / "c")
    assert (c / "meetings" / "2026-07-04-standup" / "standup.md").exists()
    assert not (c / "meetings" / "2026-07-04-standup" / "_inbox").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./.venv/bin/python -m pytest tests/test_meeting_rollup_integration.py -k roll_up_all -q`
Expected: FAIL with `ImportError: cannot import name 'roll_up_all'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# add to lib/meeting_rollup.py
from lib.gitsync import run_git, push_paths

def roll_up_all(repo, remote="origin", branch="main"):
    repo = Path(repo)
    base = repo / "meetings"
    results = []
    if not base.is_dir():
        return results
    for mdir in sorted(base.iterdir()):
        inbox = mdir / "_inbox"
        if not (mdir.is_dir() and inbox.is_dir() and any(inbox.glob("*.md"))):
            continue
        changed = roll_up(repo, mdir)
        if not changed:
            continue
        rel = f"meetings/{mdir.name}/"
        try:
            status = push_paths(repo, f"roll up {mdir.name}", [rel],
                                remote=remote, branch=branch)
            results.append((mdir.name, status))
        except RuntimeError:
            run_git(repo, "reset", "--hard", f"{remote}/{branch}")
            results.append((mdir.name, "deferred-conflict"))
    return results
```

Then wire the hook:

```python
# client-kit/.claude/hooks/sync_pull.py  -- update imports and main()
from lib.gitsync import pull
from lib.meeting_rollup import roll_up_all

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    print(pull(a.repo))
    for name, status in roll_up_all(a.repo):
        print(f"rollup {name}: {status}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS (full suite green, including the new `roll_up_all` test).

- [ ] **Step 5: Commit**

```bash
git add lib/meeting_rollup.py client-kit/.claude/hooks/sync_pull.py tests/test_meeting_rollup_integration.py
git commit -m "feat: roll_up_all transaction driver + session-start hook wiring

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: End-to-end test (two contributors -> third client rolls up; privacy preserved)

**Files:**
- Test: `tests/test_rollup_e2e.py` (new)

**Context:** Mirror `tests/test_e2e_loop.py`'s structure (`instantiate` -> `_bare_from` -> `setup_client`), but exercise the full meeting flow: two members each write a private raw transcript (must NOT sync) and publish an inbox contribution; a third member's `sync_pull` hook rolls both into one canonical note; verify the canonical note is on the remote, the inbox is gone, and neither raw transcript ever reached the remote.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_rollup_e2e.py
import subprocess, sys, json
from pathlib import Path
from tools.instantiate import instantiate
from tools.setup_client import setup_client
from lib.gitsync import run_git
from lib.meeting_rollup import SENTINEL

ROOT = Path(__file__).resolve().parents[1]

def _bare_from(local, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def _inbox_file(client, author, payload):
    mdir = client / "meetings" / "2026-07-04-standup" / "_inbox"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / f"{author}.md").write_text(
        f"{SENTINEL}\n```json\n{json.dumps(payload)}\n```\n")

def _publish(client):
    r = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "publish.py"),
         "--repo", str(client), "--allowlist", str(client / "publish_allowlist.txt"),
         "--message", "inbox"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()

def test_meeting_rollup_end_to_end(tmp_path):
    hive = instantiate(tmp_path / "acme-hive")
    remote = _bare_from(hive, tmp_path)
    alice = setup_client(str(remote), tmp_path / "alice")
    bob = setup_client(str(remote), tmp_path / "bob")
    carol = setup_client(str(remote), tmp_path / "carol")

    # raw transcripts stay private
    (alice / "private" / "personal-meetings" / "raw.md").write_text("alice raw secret\n")
    (bob / "private" / "personal-meetings" / "raw.md").write_text("bob raw secret\n")

    payload = lambda who, **kw: {"meeting_id": "2026-07-04-standup",
        "title": "Daily Standup", "date": "2026-07-04", "author": who,
        "decisions": kw.get("d", []), "action_items": [], "notes": kw.get("n", [])}
    _inbox_file(alice, "alice", payload("alice", d=["Ship v2 behind a flag"]))
    assert _publish(alice) == "pushed"
    _inbox_file(bob, "bob", payload("bob", n=["Staging is tight"]))
    # bob must catch up to alice's push first; publish does fetch-rebase-retry
    assert _publish(bob) == "pushed"

    # carol's session start: pull + roll up
    r = subprocess.run(
        [sys.executable, str(carol / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(carol)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "rollup 2026-07-04-standup: pushed" in r.stdout

    # verify on a fresh clone of the remote
    verify = tmp_path / "verify"
    subprocess.run(["git", "clone", str(remote), str(verify)], check=True)
    canon = verify / "meetings" / "2026-07-04-standup" / "standup.md"
    assert canon.exists()
    text = canon.read_text()
    assert "Ship v2 behind a flag" in text
    assert "Staging is tight" in text
    assert not (verify / "meetings" / "2026-07-04-standup" / "_inbox").exists()
    # no raw transcript ever left
    assert not (verify / "private").exists()
    assert "raw secret" not in text
```

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `./.venv/bin/python -m pytest tests/test_rollup_e2e.py -q`
Expected: initially FAIL if any wiring is off; iterate until PASS. (All library code exists by now, so this is an integration guard.)

- [ ] **Step 3: Run the full suite**

Run: `./.venv/bin/python -m pytest -q`
Expected: PASS (all tests green).

- [ ] **Step 4: Commit**

```bash
git add tests/test_rollup_e2e.py
git commit -m "test: end-to-end meeting roll-up with privacy invariant

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: The `/process-meeting` skill

**Files:**
- Create: `client-kit/.claude/skills/process-meeting/SKILL.md`
- (Create the `client-kit/.claude/skills/` directory if absent.)

**Context:** This is a thin, assistant-facing skill (Markdown instructions, not harness code). It documents the flow the assistant follows on a member's machine. It must reference the harness helpers (`slugify`, `find_meeting_dirs`) and the exact contribution file format. There is no test for a Markdown skill; correctness is that it matches the data format Task 4/7 parse. Verify by re-reading the format against `lib/meeting_rollup.py`. Delivery: `setup_client.py` already copies all of `client-kit/.claude/` into each client, so no wiring change is needed for the skill to reach members.

- [ ] **Step 1: Write the skill file**

```markdown
---
name: process-meeting
description: Turn a raw meeting transcript in private/personal-meetings/ into a shareable, structured contribution and publish it to the shared meeting inbox.
---

# Process a meeting

Use this after a meeting whose raw transcript is saved under `private/personal-meetings/`. The raw transcript NEVER leaves this machine; you publish only a structured summary.

## Steps

1. **Read the raw transcript** the member points you at (under `private/personal-meetings/`). Summarize it into three lists:
   - `decisions`: short decision statements (strings).
   - `action_items`: objects `{owner, text}` (owner is the assignee's author-id or name).
   - `notes`: other noteworthy points (strings).

2. **Refresh the shared tree before choosing an id** (so you see meetings other members already created):
   `python3 .claude/hooks/sync_pull.py --repo <repo>` (or a plain `git pull`).

3. **Discover-or-create the meeting id.** With the meeting date `YYYY-MM-DD`, list existing dirs:
   ```python
   from lib.meeting_rollup import find_meeting_dirs, slugify
   find_meeting_dirs("<repo>", "2026-07-04")
   ```
   If one plausibly matches this meeting (reconcile title variants like "standup" vs "daily standup" yourself), reuse its id. Otherwise create `<date>-<slugify(title)>`.

4. **Determine your author-id** (one stable identity, used everywhere): a handle from your `private/personal-context` profile if you have one; otherwise the slugified local-part of `git config user.email` (e.g. `alice@x.com` -> `alice`).

5. **Write the contribution** to `meetings/<id>/_inbox/<author-id>.md` with exactly this content (a sentinel comment then a fenced json block):
   ```
   <!-- team-brain-harness:rollup-data -->
   ```json
   {"meeting_id": "<id>", "title": "<title>", "date": "<date>",
    "author": "<author-id>", "decisions": [...], "action_items": [...], "notes": [...]}
   ```(closing fence)
   ```

6. **Publish** just the shared contribution (raw stays private):
   `python3 .claude/hooks/publish.py --repo <repo> --allowlist <repo>/publish_allowlist.txt --message "meeting <id>"`

The roll-up into one canonical note happens automatically on the next member's session start. You do not merge by hand.
```

(Replace `(closing fence)` with a literal triple backtick when writing the file.)

- [ ] **Step 2: Verify the skill's format matches the parser**

Run a quick round-trip check that a contribution written per the skill parses:
```bash
./.venv/bin/python -c "
from pathlib import Path
from lib.meeting_rollup import parse_payload, SENTINEL
import json, tempfile, os
d = tempfile.mkdtemp(); f = Path(d)/'alice.md'
f.write_text(SENTINEL + '\n\`\`\`json\n' + json.dumps({'meeting_id':'m','title':'t','date':'2026-07-04','author':'alice','decisions':['x'],'action_items':[],'notes':[]}) + '\n\`\`\`\n')
print(parse_payload(f)['decisions'])
"
```
Expected: `['x']`.

- [ ] **Step 3: Commit**

```bash
git add client-kit/.claude/skills/process-meeting/SKILL.md
git commit -m "feat: /process-meeting skill (raw transcript -> shared contribution)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 11: Docs update (README + getting-started reflect shipped roll-up)

**Files:**
- Modify: `README.md` (the "A day in the life" section that says roll-up is "the next sub-project"; the status line)
- Modify: `docs/getting-started.md` (add `/process-meeting` to daily use + command reference)

**Context:** Sub-project 1 docs say the roll-up "is the next sub-project (see Design below)." Flip that to shipped, add the `/process-meeting` flow to daily use, and update the status badge/line to "1-2 of 5" as appropriate. Keep the docs genericized (no employer/personal specifics). Do not overclaim: state that summarization is assistant-driven via the skill.

- [ ] **Step 1: Update README.md**
  - In "A day in the life: the standup", change the closing paragraph that defers roll-up to the next sub-project; state the roll-up now works and is driven by `/process-meeting` + the session-start hook.
  - Update the status badge and the "Status: this repo implements sub-project 1 of 5" line to reflect sub-project 2 is done, listing the remaining as 3) control plane, 4) TTL/freshness, 5) installer/onboarding.

- [ ] **Step 2: Update docs/getting-started.md**
  - In "Part C: Daily use", add a subsection documenting `/process-meeting` (summarize a private transcript -> publish a contribution; roll-up is automatic on session start).
  - Add a row to the command-reference table:
    | Process a meeting into a shared contribution | run the `/process-meeting` skill in your assistant |

- [ ] **Step 3: Verify no stale roll-up-deferral claim remains**

Run: `grep -rni "roll-up.*next sub-project\|is the next sub-project" README.md docs/getting-started.md`
Expected: no results (the sentence deferring roll-up to a future sub-project is gone). Separately confirm the status line now credits sub-project 2 as done.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/getting-started.md
git commit -m "docs: mark meeting roll-up shipped; document /process-meeting

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final: after all tasks

- [ ] Run the full suite once more: `./.venv/bin/python -m pytest -q` (expect all green).
- [ ] Use **superpowers:finishing-a-development-branch** to complete the branch. Given `main` is branch-protected, the expected path is **Option 2 (push and open a PR)** for your own review/merge, not a local merge to `main`.
