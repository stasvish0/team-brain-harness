from lib.meeting_rollup import (slugify, normalize, content_hash, merge,
                                render, parse_payload, SENTINEL)


def test_slugify_lowercases_and_hyphenates():
    assert slugify("Daily Standup") == "daily-standup"

def test_slugify_strips_punctuation_and_collapses():
    assert slugify("  Weekly  Sync!! (Eng) ") == "weekly-sync-eng"

def test_slugify_unicode_is_dropped_to_ascii_words():
    assert slugify("Café review") == "caf-review"

def test_normalize_lowercases_collapses_ws_and_strips_trailing_punct():
    assert normalize("  Ship  v2  behind a flag. ") == "ship v2 behind a flag"
    assert normalize("Wire the feature flag!!!") == "wire the feature flag"


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
    b_with_by = _payload(decisions=[{"text": "Ship v2 behind a flag", "by": ["x"]}])
    assert content_hash(a) == content_hash(b_with_by)

def test_content_hash_changes_when_a_decision_changes():
    a = _payload()
    b = _payload(decisions=["Ship v2 behind a feature flag"])
    assert content_hash(a) != content_hash(b)

def test_content_hash_is_order_independent():
    a = _payload(notes=["one", "two"])
    b = _payload(notes=["two", "one"])
    assert content_hash(a) == content_hash(b)


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
    assert out["decisions"] == [{"text": "Ship v2 behind a flag", "by": ["alice", "bob"]}]
    assert out["action_items"] == [
        {"owner": "bob", "text": "Wire the feature flag", "by": ["alice"]}]
    assert out["notes"] == [{"text": "Staging is tight", "by": ["bob"]}]
    assert {e["author"] for e in out["merged_authors"]} == {"alice", "bob"}
    assert out["meeting_id"] == "2026-07-04-standup"

def test_merge_is_idempotent_on_already_folded_contribution():
    a = _contrib("alice", decisions=["Ship v2 behind a flag"])
    once = merge(None, [a])
    twice = merge(once, [a])
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
    assert sum(1 for e in second["merged_authors"] if e["author"] == "alice") == 2


def test_render_is_byte_identical_regardless_of_processing_order():
    a = _contrib("alice", decisions=["B decision"], notes=["z note"])
    b = _contrib("bob", decisions=["A decision"], notes=["a note"])
    p1 = merge(None, [a, b])
    p2 = merge(None, [b, a])
    assert render(p1) == render(p2)

def test_render_body_has_sections_and_sorted_items():
    p = merge(None, [_contrib("alice", decisions=["B", "A"])])
    text = render(p)
    body = text.split(SENTINEL)[0]
    assert "## Decisions" in body
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
