"""Deterministic meeting roll-up: merge author-namespaced inbox contributions
into one canonical note per meeting. Stdlib only. See
docs/superpowers/specs/2026-07-04-meeting-rollup-design.md."""
import hashlib
import json
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
