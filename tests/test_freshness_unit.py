from datetime import date

import pytest

from lib.freshness import read_health_config, parse_frontmatter, DEFAULT_SCAN_ROOTS, note_status, scan, stamp
from lib.freshness import find_duplicates

CFG = {"default_horizon_days": 180, "horizons": {"project": 30, "decision": 365}}


def test_read_health_config_default_when_missing(tmp_path):
    cfg = read_health_config(tmp_path)
    assert cfg["default_horizon_days"] == 180
    assert cfg["horizons"] == {}
    assert cfg["scan_roots"] == DEFAULT_SCAN_ROOTS
    assert "private" in cfg["scan_roots"]


def test_read_health_config_reads_file(tmp_path):
    import json
    (tmp_path / "CONTROL").mkdir()
    (tmp_path / "CONTROL" / "health.json").write_text(json.dumps(
        {"default_horizon_days": 90, "horizons": {"project": 30}, "scan_roots": ["engineering"]}))
    cfg = read_health_config(tmp_path)
    assert cfg["default_horizon_days"] == 90 and cfg["horizons"]["project"] == 30
    assert cfg["scan_roots"] == ["engineering"]


def test_parse_frontmatter_scalars_quotes_comments(tmp_path):
    f = tmp_path / "n.md"
    f.write_text('---\ntitle: "Adopt X # 2"\ntype: decision\n'
                 'last_verified: 2026-07-05  # stamped\nreview_by: 2026-12-31\n---\nbody\n')
    fm = parse_frontmatter(f)
    assert fm["title"] == "Adopt X # 2"   # '#' inside quotes is preserved
    assert fm["type"] == "decision"
    assert fm["last_verified"] == "2026-07-05"   # inline comment stripped
    assert fm["review_by"] == "2026-12-31"


def test_parse_frontmatter_none_when_no_block(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("# Just a heading\nno front-matter\n")
    assert parse_frontmatter(f) is None


def test_parse_frontmatter_missing_last_verified(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("---\ntitle: x\ntype: reference\n---\nbody\n")
    fm = parse_frontmatter(f)
    assert fm is not None and "last_verified" not in fm


def test_parse_frontmatter_empty_value_does_not_crash(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("---\ntitle:\nreview_by:\ntype: reference\nlast_verified: 2026-07-05\n---\nbody\n")
    fm = parse_frontmatter(f)  # must not raise
    assert fm["title"] == ""
    assert fm["review_by"] == ""
    assert fm["last_verified"] == "2026-07-05"


def test_status_fresh_within_horizon():
    fm = {"type": "project", "last_verified": "2026-07-01"}
    assert note_status(fm, date(2026, 7, 5), CFG) == "fresh"


def test_status_stale_past_horizon():
    fm = {"type": "project", "last_verified": "2026-05-01"}
    assert note_status(fm, date(2026, 7, 5), CFG) == "stale"


def test_status_horizon_boundary_is_strict():
    fm = {"type": "project", "last_verified": "2026-06-05"}  # exactly 30 days
    assert note_status(fm, date(2026, 7, 5), CFG) == "fresh"


def test_status_uses_default_horizon_for_unknown_type():
    fm = {"type": "mystery", "last_verified": "2026-01-01"}  # >180d
    assert note_status(fm, date(2026, 7, 5), CFG) == "stale"


def test_status_expired_review_by_exclusive():
    fm = {"type": "decision", "last_verified": "2026-07-01", "review_by": "2026-07-05"}
    assert note_status(fm, date(2026, 7, 5), CFG) == "fresh"   # on review_by day: not yet expired
    assert note_status(fm, date(2026, 7, 6), CFG) == "expired" # day after: expired


def test_status_untracked_when_no_last_verified():
    assert note_status({"type": "project"}, date(2026, 7, 5), CFG) is None


def _note(root, rel, lv, type_="reference", extra=""):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntype: {type_}\nlast_verified: {lv}\n{extra}---\nbody\n")


def test_scan_classifies_and_skips_untracked(tmp_path):
    cfg = {"default_horizon_days": 180, "horizons": {}, "scan_roots": ["engineering", "nope"]}
    _note(tmp_path, "engineering/fresh.md", "2026-07-01")
    _note(tmp_path, "engineering/stale.md", "2025-01-01")
    (tmp_path / "engineering" / "plain.md").write_text("# no frontmatter\n")
    results = scan(tmp_path, cfg, date(2026, 7, 5))
    by_path = {r["path"]: r for r in results}
    assert set(by_path) == {"engineering/fresh.md", "engineering/stale.md"}
    assert by_path["engineering/fresh.md"]["status"] == "fresh"
    assert by_path["engineering/stale.md"]["status"] == "stale"
    assert by_path["engineering/stale.md"]["age_days"] > 180


def test_scan_missing_root_is_silent(tmp_path):
    cfg = {"default_horizon_days": 180, "horizons": {}, "scan_roots": ["ghost"]}
    assert scan(tmp_path, cfg, date(2026, 7, 5)) == []


def test_stamp_updates_only_last_verified(tmp_path):
    f = tmp_path / "n.md"
    f.write_text('---\ntitle: "Keep Me"\ntype: decision\n'
                 'last_verified: 2025-01-01\nreview_by: 2026-12-31\n---\n# Keep Me\nbody line\n')
    stamp(f, date(2026, 7, 5))
    text = f.read_text()
    assert "last_verified: 2026-07-05" in text
    assert "2025-01-01" not in text
    assert 'title: "Keep Me"' in text
    assert "review_by: 2026-12-31" in text
    assert "# Keep Me\nbody line\n" in text


def test_stamp_is_idempotent(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("---\ntype: reference\nlast_verified: 2026-07-05\n---\nbody\n")
    before = f.read_text()
    stamp(f, date(2026, 7, 5))
    assert f.read_text() == before


def test_stamp_raises_without_last_verified_line(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("---\ntype: reference\n---\nbody\n")
    with pytest.raises(ValueError):
        stamp(f, date(2026, 7, 5))


def test_find_duplicates_clusters_near_identical(tmp_path):
    cfg = {"scan_roots": ["knowledge"], "default_horizon_days": 180, "horizons": {}}
    _note(tmp_path, "knowledge/a.md", "2026-07-01", extra="")  # body "body"
    _note(tmp_path, "knowledge/b.md", "2026-06-01", extra="")  # body "body" (dup, diff frontmatter)
    (tmp_path / "knowledge" / "c.md").write_text(
        "---\ntype: reference\nlast_verified: 2026-07-01\n---\ntotally different content\n")
    clusters = find_duplicates(tmp_path, cfg)
    assert clusters == [["knowledge/a.md", "knowledge/b.md"]]


def test_find_duplicates_none_when_all_distinct(tmp_path):
    cfg = {"scan_roots": ["knowledge"], "default_horizon_days": 180, "horizons": {}}
    (tmp_path / "knowledge").mkdir(parents=True)
    (tmp_path / "knowledge" / "a.md").write_text("---\nlast_verified: 2026-07-01\n---\nalpha\n")
    (tmp_path / "knowledge" / "b.md").write_text("---\nlast_verified: 2026-07-01\n---\nbeta\n")
    assert find_duplicates(tmp_path, cfg) == []


def test_stamp_ignores_body_line_that_looks_like_frontmatter(tmp_path):
    f = tmp_path / "n.md"
    f.write_text("---\ntype: reference\nlast_verified: 2025-01-01\n---\n"
                 "prose mentioning last_verified: 2099-12-31 in the body\n")
    stamp(f, date(2026, 7, 5))
    text = f.read_text()
    # only the front-matter line was updated
    assert "last_verified: 2026-07-05" in text
    assert "last_verified: 2099-12-31 in the body" in text  # body untouched
    assert "2025-01-01" not in text
