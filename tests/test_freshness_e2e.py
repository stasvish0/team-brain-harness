import subprocess, sys
from datetime import date
from pathlib import Path
from tools.instantiate import instantiate
from tools.setup_client import setup_client
from lib.gitsync import run_git
from lib.freshness import commit_stamps

def _bare_from(local, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def test_stale_note_flagged_then_stamped_seen_fresh(tmp_path):
    hive = instantiate(tmp_path / "hive")
    (hive / "engineering" / "adr-001.md").write_text(
        "---\ntype: decision\nlast_verified: 2020-01-01\n---\n# old\n")
    run_git(hive, "add", "-A"); run_git(hive, "commit", "-m", "old note")
    remote = _bare_from(hive, tmp_path)
    client = setup_client(str(remote), tmp_path / "client")

    r = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "STALE" in r.stdout and "engineering/adr-001.md" in r.stdout

    commit_stamps(client, ["engineering/adr-001.md"], date.today())

    client2 = setup_client(str(remote), tmp_path / "client2")
    r2 = subprocess.run(
        [sys.executable, str(client2 / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client2)], capture_output=True, text=True)
    assert r2.returncode == 0, r2.stderr
    assert "engineering/adr-001.md" not in r2.stdout
