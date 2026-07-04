import subprocess
from pathlib import Path
from lib.gitsync import publish, run_git

def _clone(bare, dest, email):
    subprocess.run(["git", "clone", str(bare), str(dest)], check=True)
    run_git(dest, "config", "user.email", email)
    run_git(dest, "config", "user.name", email)

def test_concurrent_publish_no_overwrite(bare_remote, tmp_path):
    a = tmp_path / "a"; _clone(bare_remote, a, "alice@x")
    b = tmp_path / "b"; _clone(bare_remote, b, "bob@x")

    # Bob pushes first, out of band
    (b / "engineering").mkdir(); (b / "engineering" / "bob.md").write_text("bob\n")
    run_git(b, "add", "-A"); run_git(b, "commit", "-m", "bob"); run_git(b, "push", "origin", "main")

    # Alice publishes her own (disjoint) file; her first push will be rejected,
    # then rebase+retry must succeed and preserve Bob's file.
    (a / "engineering").mkdir(exist_ok=True); (a / "engineering" / "alice.md").write_text("alice\n")
    result = publish(a, "alice", ["engineering/"])
    assert result == "pushed"

    # Verify both files exist on the remote (via a fresh clone)
    c = tmp_path / "c"
    subprocess.run(["git", "clone", str(bare_remote), str(c)], check=True)
    assert (c / "engineering" / "bob.md").exists()
    assert (c / "engineering" / "alice.md").exists()
