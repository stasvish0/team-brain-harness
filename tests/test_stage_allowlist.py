import subprocess
from pathlib import Path
from lib.gitsync import stage_allowlist, run_git

def _clone(bare, dest):
    subprocess.run(["git", "clone", str(bare), str(dest)], check=True)
    run_git(dest, "config", "user.email", "a@b.c")
    run_git(dest, "config", "user.name", "A")

def test_only_allowlisted_paths_are_staged(bare_remote, tmp_path):
    clone = tmp_path / "c"; _clone(bare_remote, clone)
    (clone / "engineering").mkdir()
    (clone / "engineering" / "note.md").write_text("shared\n")
    (clone / "private").mkdir()
    (clone / "private" / "secret.md").write_text("PRIVATE\n")
    (clone / ".gitignore").write_text("/private/\n")
    run_git(clone, "add", ".gitignore"); run_git(clone, "commit", "-m", "ignore")

    stage_allowlist(clone, ["engineering/"])
    staged = run_git(clone, "diff", "--cached", "--name-only").stdout.split()
    assert "engineering/note.md" in staged
    assert not any("private" in s for s in staged)
