import subprocess
import pytest
from pathlib import Path
from lib.gitsync import publish, pull, run_git

def _clone(bare, dest, email):
    subprocess.run(["git", "clone", str(bare), str(dest)], check=True)
    run_git(dest, "config", "user.email", email); run_git(dest, "config", "user.name", email)

def _no_rebase_in_progress(repo):
    return not (repo / ".git" / "rebase-merge").exists() and not (repo / ".git" / "rebase-apply").exists()

def test_publish_conflict_raises_and_leaves_repo_clean(bare_remote, tmp_path):
    a = tmp_path / "a"; _clone(bare_remote, a, "alice@x")
    b = tmp_path / "b"; _clone(bare_remote, b, "bob@x")
    # both edit the SAME file on the same base
    (b / "engineering").mkdir(); (b / "engineering" / "shared.md").write_text("bob version\n")
    run_git(b, "add", "-A"); run_git(b, "commit", "-m", "bob"); run_git(b, "push", "origin", "main")
    (a / "engineering").mkdir(exist_ok=True); (a / "engineering" / "shared.md").write_text("alice version\n")
    with pytest.raises(RuntimeError):
        publish(a, "alice", ["engineering/"])
    assert _no_rebase_in_progress(a)

def test_pull_conflict_raises_and_leaves_repo_clean(bare_remote, tmp_path):
    a = tmp_path / "a"; _clone(bare_remote, a, "alice@x")
    b = tmp_path / "b"; _clone(bare_remote, b, "bob@x")
    (b / "product").mkdir(); (b / "product" / "x.md").write_text("bob\n")
    run_git(b, "add", "-A"); run_git(b, "commit", "-m", "bob"); run_git(b, "push", "origin", "main")
    # Alice makes a conflicting local commit on the same file, unpushed
    (a / "product").mkdir(exist_ok=True); (a / "product" / "x.md").write_text("alice\n")
    run_git(a, "add", "-A"); run_git(a, "commit", "-m", "alice local")
    with pytest.raises(RuntimeError):
        pull(a)
    assert _no_rebase_in_progress(a)
