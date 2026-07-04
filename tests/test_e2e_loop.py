import subprocess, sys
from pathlib import Path
from tools.instantiate import instantiate
from tools.setup_client import setup_client
from lib.gitsync import run_git, pull

ROOT = Path(__file__).resolve().parents[1]  # repo root, relative to tests/

def _bare_from(local, tmp_path):
    """Publish a local repo to a fresh bare remote and return the remote path."""
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def test_full_loop(tmp_path):
    # 1. instantiate a live hive and publish it to a bare "GitHub"
    hive = instantiate(tmp_path / "acme-hive")
    remote = _bare_from(hive, tmp_path)

    # 2. two members set up clients
    alice = setup_client(str(remote), tmp_path / "alice")
    bob = setup_client(str(remote), tmp_path / "bob")

    # 3. Alice writes a private note (must never sync) and a shared note (must sync)
    (alice / "private" / "personal-context" / "me.md").write_text("my growth goals\n")
    (alice / "engineering" / "adr-001.md").write_text("decision\n")

    # 4. Alice publishes via the hook
    r = subprocess.run([sys.executable, str(alice / ".claude" / "hooks" / "publish.py"),
                        "--repo", str(alice), "--allowlist", str(alice / "publish_allowlist.txt"),
                        "--message", "adr"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "pushed", r.stdout  # not "nothing-to-publish"

    # 5. Bob pulls and sees the shared note but NOT Alice's private note
    pull(bob)
    assert (bob / "engineering" / "adr-001.md").exists()
    assert not (bob / "private" / "personal-context" / "me.md").exists()

    # 6. The private note never reached the remote
    checkout = tmp_path / "verify"
    subprocess.run(["git", "clone", str(remote), str(checkout)], check=True)
    assert not (checkout / "private").exists()
