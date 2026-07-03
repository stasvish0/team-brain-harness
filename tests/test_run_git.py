from lib.gitsync import run_git

def test_run_git_returns_output(bare_remote, tmp_path):
    clone = tmp_path / "c"
    import subprocess
    subprocess.run(["git", "clone", str(bare_remote), str(clone)], check=True)
    result = run_git(clone, "rev-parse", "--abbrev-ref", "HEAD")
    assert result.stdout.strip() == "main"
