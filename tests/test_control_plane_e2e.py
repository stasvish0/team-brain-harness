import json, subprocess, sys
from pathlib import Path
from tools.instantiate import instantiate
from tools.setup_client import setup_client
from lib.gitsync import run_git

def _bare_from(local, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def test_admin_change_converges_on_client(tmp_path):
    hive = instantiate(tmp_path / "hive")
    remote = _bare_from(hive, tmp_path)
    client = setup_client(str(remote), tmp_path / "client")

    man = json.loads((hive / "CONTROL" / "manifest.json").read_text())
    man["skills_version"] += 1
    man["structure_version"] = 1
    man["policy_version"] += 1
    man["required_mcps"] = [{"name": "granola", "how": "authorize in settings"}]
    (hive / "CONTROL" / "manifest.json").write_text(json.dumps(man))
    sk = hive / "CONTROL" / "skills" / "newskill"; sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text("new")
    (hive / "CONTROL" / "migrations").mkdir(exist_ok=True)
    (hive / "CONTROL" / "migrations" / "0001-add-legal.json").write_text(json.dumps(
        {"ops": [{"op": "keep_file", "path": "engineering/legal/.gitkeep"}]}))
    (hive / "CONTROL" / "policy.md").write_text("new standing rules\n")
    run_git(hive, "add", "-A"); run_git(hive, "commit", "-m", "admin: bump control plane")
    run_git(hive, "push", "origin", "main")

    r = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (client / ".claude" / "skills" / "newskill" / "SKILL.md").exists()
    assert (client / "engineering" / "legal" / ".gitkeep").exists()
    assert "NEW MCP required: granola" in r.stdout
    assert "new standing rules" in r.stdout

    verify = tmp_path / "verify"
    subprocess.run(["git", "clone", str(remote), str(verify)], check=True)
    assert (verify / "engineering" / "legal" / ".gitkeep").exists()

    r2 = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client)], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert "NEW MCP required" not in r2.stdout
