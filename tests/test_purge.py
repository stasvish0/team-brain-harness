import subprocess
from pathlib import Path
from lib.gitsync import run_git
from tests.conftest import init_identity
from tools.purge import purge

def test_purge_removes_path_from_all_history(tmp_path):
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True)
    init_identity(repo)
    (repo / "secret.txt").write_text("leaked token\n")
    (repo / "keep.txt").write_text("fine\n")
    run_git(repo, "add", "-A"); run_git(repo, "commit", "-m", "with secret")
    (repo / "later.txt").write_text("more\n")
    run_git(repo, "add", "-A"); run_git(repo, "commit", "-m", "later")

    purge(repo, "secret.txt", force=True)

    objs = run_git(repo, "rev-list", "--all", "--objects").stdout
    assert "secret.txt" not in objs
    assert (repo / "keep.txt").exists()

def test_purge_dry_run_does_not_change_history(tmp_path):
    repo = tmp_path / "r"
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True)
    init_identity(repo)
    (repo / "secret.txt").write_text("leaked\n")
    run_git(repo, "add", "-A"); run_git(repo, "commit", "-m", "x")
    before = run_git(repo, "rev-parse", "HEAD").stdout
    purge(repo, "secret.txt", force=False)
    after = run_git(repo, "rev-parse", "HEAD").stdout
    assert before == after
