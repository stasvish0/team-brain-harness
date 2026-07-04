"""Deterministic meeting roll-up: merge author-namespaced inbox contributions
into one canonical note per meeting. Stdlib only. See
docs/superpowers/specs/2026-07-04-meeting-rollup-design.md."""
import hashlib
import json
import re
from pathlib import Path

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
    after = text.split(SENTINEL, 1)[1]
    m = re.search(r"```json\n(.*?)\n```", after, re.DOTALL)
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
