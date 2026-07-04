import subprocess
from pathlib import Path
from lib.gitsync import pull, run_git

def _clone(bare, dest, email):
    subprocess.run(["git", "clone", str(bare), str(dest)], check=True)
    run_git(dest, "config", "user.email", email); run_git(dest, "config", "user.name", email)

def test_pull_sees_others_changes(bare_remote, tmp_path):
    a = tmp_path / "a"; _clone(bare_remote, a, "a@x")
    b = tmp_path / "b"; _clone(bare_remote, b, "b@x")
    (a / "product").mkdir(); (a / "product" / "roadmap.md").write_text("v1\n")
    run_git(a, "add", "-A"); run_git(a, "commit", "-m", "roadmap"); run_git(a, "push", "origin", "main")
    pull(b)
    assert (b / "product" / "roadmap.md").read_text() == "v1\n"
