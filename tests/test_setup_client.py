from pathlib import Path
from tools.setup_client import setup_client

def test_setup_client_creates_private_tree_and_hooks(bare_remote, tmp_path):
    clone = tmp_path / "me"
    setup_client(str(bare_remote), clone)
    for d in ["personal-meetings", "personal-context", "personal-decisions",
              "personal-docs", "personal-drafts", "personal-projects", "personal-reviews"]:
        assert (clone / "private" / d).is_dir()
    assert (clone / "private" / "TODO.md").is_file()
    assert (clone / ".claude" / "hooks" / "publish.py").is_file()
    assert (clone / "lib" / "gitsync.py").is_file()
    import subprocess
    out = subprocess.run(["git", "-C", str(clone), "status", "--porcelain"],
                         capture_output=True, text=True, check=True).stdout
    assert "private/" not in out
