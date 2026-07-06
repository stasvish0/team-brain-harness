import subprocess
from datetime import date
from pathlib import Path
from lib.gitsync import run_git
from lib.freshness import commit_stamps, freshness_report
from tests.conftest import init_identity

def _clone(remote, dest):
    subprocess.run(["git", "clone", str(remote), str(dest)], check=True)
    init_identity(dest)
    return dest

def _tracked(repo, rel, lv):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\ntype: reference\nlast_verified: {lv}\n---\nbody\n")

def test_commit_stamps_pushes_shared_only(bare_remote, tmp_path):
    a = _clone(bare_remote, tmp_path / "a")
    _tracked(a, "engineering/adr.md", "2025-01-01")
    (a / "private" / "personal-context").mkdir(parents=True)
    _tracked(a, "private/personal-context/me.md", "2025-01-01")
    run_git(a, "add", "engineering"); run_git(a, "commit", "-m", "seed note")
    run_git(a, "push", "origin", "main")

    shared = commit_stamps(a, ["engineering/adr.md", "private/personal-context/me.md"],
                           date(2026, 7, 5))
    assert shared == ["engineering/adr.md"]
    v = _clone(bare_remote, tmp_path / "v")
    assert "last_verified: 2026-07-05" in (v / "engineering" / "adr.md").read_text()
    assert not (v / "private").exists()

def test_commit_stamps_push_conflict_propagates_and_resets(bare_remote, tmp_path, monkeypatch):
    a = _clone(bare_remote, tmp_path / "a")
    _tracked(a, "engineering/adr.md", "2025-01-01")
    run_git(a, "add", "engineering"); run_git(a, "commit", "-m", "seed"); run_git(a, "push", "origin", "main")
    import lib.freshness as fr
    monkeypatch.setattr(fr, "push_paths",
                        lambda *args, **kw: (_ for _ in ()).throw(RuntimeError("conflict")))
    import pytest
    with pytest.raises(RuntimeError):
        commit_stamps(a, ["engineering/adr.md"], date(2026, 7, 5))
    assert run_git(a, "status", "--porcelain").stdout.strip() == ""
    assert "last_verified: 2025-01-01" in (a / "engineering" / "adr.md").read_text()

def test_freshness_report_lists_stale_and_expired(tmp_path):
    import json
    (tmp_path / "CONTROL").mkdir()
    (tmp_path / "CONTROL" / "health.json").write_text(json.dumps(
        {"default_horizon_days": 180, "horizons": {}, "scan_roots": ["engineering"]}))
    _tracked(tmp_path, "engineering/old.md", "2025-01-01")  # stale vs today
    lines = freshness_report(tmp_path, date(2026, 7, 5))
    assert any("freshness:" in ln and "stale" in ln for ln in lines)
    assert any("engineering/old.md" in ln for ln in lines)

def test_freshness_report_empty_when_all_fresh(tmp_path):
    import json
    (tmp_path / "CONTROL").mkdir()
    (tmp_path / "CONTROL" / "health.json").write_text(json.dumps(
        {"default_horizon_days": 180, "horizons": {}, "scan_roots": ["engineering"]}))
    _tracked(tmp_path, "engineering/new.md", "2026-07-01")
    assert freshness_report(tmp_path, date(2026, 7, 5)) == []
