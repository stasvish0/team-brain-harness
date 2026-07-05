import json, subprocess
from pathlib import Path
from lib.gitsync import run_git, push_paths
from lib.control_plane import apply_control_plane, read_applied
import lib.control_plane as cp
from tests.conftest import init_identity

def _hive(bare_remote, tmp_path, name, manifest, allowlist="CONTROL/\nengineering/\n"):
    d = tmp_path / name
    subprocess.run(["git", "clone", str(bare_remote), str(d)], check=True)
    init_identity(d)
    (d / "CONTROL").mkdir(exist_ok=True)
    (d / "CONTROL" / "manifest.json").write_text(json.dumps(manifest))
    (d / "publish_allowlist.txt").write_text(allowlist)
    return d

def _manifest(**over):
    m = {"skills_version": 0, "structure_version": 0, "min_client_version": "0.0.1",
         "required_mcps": [], "policy_version": 0}
    m.update(over); return m

def test_gated_session_applies_nothing_and_writes_block(bare_remote, tmp_path):
    d = _hive(bare_remote, tmp_path, "c", _manifest(min_client_version="9.9.9"))
    res = apply_control_plane(d)
    assert res["blocked"] is True and res["gate_reasons"]
    assert (d / ".control-block").exists()

def test_migration_applied_committed_and_pushed(bare_remote, tmp_path):
    d = _hive(bare_remote, tmp_path, "c", _manifest(structure_version=1))
    md = d / "CONTROL" / "migrations"; md.mkdir(parents=True)
    (md / "0001-add-eng.json").write_text(json.dumps(
        {"ops": [{"op": "make_dir", "path": "engineering/adr"},
                 {"op": "keep_file", "path": "engineering/adr/.gitkeep"}]}))
    run_git(d, "add", "-A"); run_git(d, "commit", "-m", "seed migration")
    run_git(d, "push", "origin", "main")
    res = apply_control_plane(d)
    assert res["blocked"] is False
    assert (d / "engineering" / "adr" / ".gitkeep").exists()
    assert read_applied(d)["structure_version"] == 1
    verify = tmp_path / "verify"
    subprocess.run(["git", "clone", str(bare_remote), str(verify)], check=True)
    assert (verify / "engineering" / "adr" / ".gitkeep").exists()

def test_second_client_noops_already_migrated_tree(bare_remote, tmp_path):
    d = _hive(bare_remote, tmp_path, "c", _manifest(structure_version=1))
    md = d / "CONTROL" / "migrations"; md.mkdir(parents=True)
    (md / "0001-add-eng.json").write_text(json.dumps(
        {"ops": [{"op": "keep_file", "path": "engineering/adr/.gitkeep"}]}))
    run_git(d, "add", "-A"); run_git(d, "commit", "-m", "seed"); run_git(d, "push", "origin", "main")
    apply_control_plane(d)
    d2 = tmp_path / "c2"
    subprocess.run(["git", "clone", str(bare_remote), str(d2)], check=True)
    init_identity(d2)
    (d2 / "publish_allowlist.txt").write_text("CONTROL/\nengineering/\n")
    res = apply_control_plane(d2)
    assert res["blocked"] is False
    assert read_applied(d2)["structure_version"] == 1

def test_skills_and_mcp_and_policy_applied(bare_remote, tmp_path):
    d = _hive(bare_remote, tmp_path, "c",
              _manifest(skills_version=1, policy_version=1,
                        required_mcps=[{"name": "granola", "how": "auth in settings"}]))
    sk = d / "CONTROL" / "skills" / "demo"; sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("demo")
    (d / "CONTROL" / "policy.md").write_text("standing rules\n")
    res = apply_control_plane(d)
    assert (d / ".claude" / "skills" / "demo" / "SKILL.md").exists()
    assert [m["name"] for m in res["mcp_announcements"]] == ["granola"]
    assert "standing rules" in res["policy_text"]
    ap = read_applied(d)
    assert ap["skills_version"] == 1 and ap["policy_version"] == 1
    assert ap["announced_mcps"] == ["granola"]
    res2 = apply_control_plane(d)
    assert res2["mcp_announcements"] == []

def test_deferred_push_leaves_clean_tree_and_unadvanced(bare_remote, tmp_path, monkeypatch):
    d = _hive(bare_remote, tmp_path, "c", _manifest(structure_version=1))
    md = d / "CONTROL" / "migrations"; md.mkdir(parents=True)
    (md / "0001-add-eng.json").write_text(json.dumps(
        {"ops": [{"op": "keep_file", "path": "engineering/adr/.gitkeep"}]}))
    run_git(d, "add", "-A"); run_git(d, "commit", "-m", "seed"); run_git(d, "push", "origin", "main")
    # force the migration push to fail as if a concurrent conflict occurred
    def _boom(*a, **k):
        raise RuntimeError("simulated push conflict")
    monkeypatch.setattr(cp, "push_paths", _boom)
    res = cp.apply_control_plane(d)
    assert res["deferred"] is True
    # tree must be genuinely clean (no untracked migration residue) so the next pull works
    porcelain = run_git(d, "status", "--porcelain").stdout.strip()
    assert porcelain == "", f"dirty tree: {porcelain}"
    assert not (d / "engineering" / "adr" / ".gitkeep").exists()
    # bookkeeping not advanced: fresh clone has no .applied.json, so read_applied
    # returns the default structure_version 0, and the deferred path must not advance it
    assert cp.read_applied(d)["structure_version"] == 0
