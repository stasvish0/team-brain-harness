from lib.meeting_rollup import slugify, normalize, content_hash


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
