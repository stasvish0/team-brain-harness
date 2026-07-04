"""Deterministic meeting roll-up: merge author-namespaced inbox contributions
into one canonical note per meeting. Stdlib only. See
docs/superpowers/specs/2026-07-04-meeting-rollup-design.md."""
import hashlib
import json
import re
from pathlib import Path

from lib.gitsync import run_git, push_paths

def slugify(title):
    """Lowercase, keep word chars, collapse the rest to single hyphens."""
    s = re.sub(r"[^a-z0-9]+", "-", title.lower())
    return s.strip("-")

def normalize(text):
    """Dedupe key for free text: lowercase, collapse whitespace, strip
    trailing punctuation."""
    s = re.sub(r"\s+", " ", text.strip().lower())
    return s.rstrip(".!?,;: ").strip()

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

# --- merge ------------------------------------------------------------------

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
    """Fold contributions into a canonical payload. Skips any contribution
    whose content_hash is already in the ledger (idempotent). Additive:
    dedupes by normalized text, unions `by` attribution, appends the ledger."""
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

# --- render / parse ---------------------------------------------------------

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
    header = f"# {p.get('title') or p.get('meeting_id')} - {p.get('date') or ''}".rstrip()
    lines = [header, "", "## Decisions"]
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
    text = Path(path).read_text()
    if SENTINEL not in text:
        return None
    # The machine block is always LAST in the file. rsplit + end-anchor avoids
    # locking onto a decoy sentinel+fence that appears inside human body text.
    after = text.rsplit(SENTINEL, 1)[1]
    m = re.search(r"```json\n(.*?)\n```\s*$", after, re.DOTALL)
    if not m:
        return None
    return json.loads(m.group(1))

# --- meeting-id discovery ---------------------------------------------------

def find_meeting_dirs(repo, date):
    """Existing meeting dirs whose name starts with the date (for the skill's
    discover-or-create step). Returns sorted Paths under <repo>/meetings/."""
    base = Path(repo) / "meetings"
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir()
                  if p.is_dir() and p.name.startswith(date + "-"))

# --- roll-up ----------------------------------------------------------------

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
    """Fold this meeting's inbox contributions into the canonical note and
    delete the folded inbox files. Returns True when something changed (a
    to-be-committed transaction), False when there is nothing new to fold."""
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

def roll_up_all(repo, remote="origin", branch="main"):
    """Session-start transaction driver: for each meeting inbox with new
    contributions, roll up and push as an independent per-meeting transaction.
    On a push conflict, reset hard to the remote tip (restoring the inbox for a
    later retry) and continue. Returns [(meeting_name, status), ...]."""
    repo = Path(repo)
    base = repo / "meetings"
    results = []
    if not base.is_dir():
        return results
    for mdir in sorted(base.iterdir()):
        inbox = mdir / "_inbox"
        if not (mdir.is_dir() and inbox.is_dir() and any(inbox.glob("*.md"))):
            continue
        if not roll_up(repo, mdir):
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
