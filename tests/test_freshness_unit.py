from datetime import date

from lib.freshness import read_health_config, parse_frontmatter, DEFAULT_SCAN_ROOTS, note_status

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
