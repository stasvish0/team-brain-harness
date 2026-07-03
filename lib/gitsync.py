import subprocess

def run_git(repo, *args, check=True):
    """Run `git -C <repo> <args>`; return the CompletedProcess."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )
