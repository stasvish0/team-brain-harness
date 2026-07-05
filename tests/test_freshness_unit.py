from lib.freshness import read_health_config, parse_frontmatter, DEFAULT_SCAN_ROOTS


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
