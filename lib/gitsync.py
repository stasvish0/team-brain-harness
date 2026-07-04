import subprocess

def run_git(repo, *args, check=True):
    """Run `git -C <repo> <args>`; return the CompletedProcess."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, check=check,
    )

def stage_allowlist(repo, allow_paths):
    """Stage only the given pathspecs. Private paths are gitignored, so even a
    stray pathspec cannot stage them; the allowlist is the primary guard and
    gitignore is the backstop."""
    for p in allow_paths:
        # check=False so a missing/empty pathspec does not abort the whole publish
        run_git(repo, "add", "--", p, check=False)

def read_allowlist(path):
    lines = []
    with open(path) as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip()
            if line:
                lines.append(line)
    return lines

def publish(repo, message, allow_paths, remote="origin", branch="main", max_retries=5):
    """Stage allowlisted paths, commit if there is anything, then push with
    fetch->rebase->retry so a concurrent push is caught up to, never clobbered."""
    stage_allowlist(repo, allow_paths)
    staged = run_git(repo, "diff", "--cached", "--name-only").stdout.strip()
    if not staged:
        return "nothing-to-publish"
    run_git(repo, "commit", "-m", message)
    for _ in range(max_retries):
        push = run_git(repo, "push", remote, branch, check=False)
        if push.returncode == 0:
            return "pushed"
        # rejected (likely non-fast-forward): catch up and retry
        run_git(repo, "fetch", remote, branch)
        rebase = run_git(repo, "rebase", f"{remote}/{branch}", check=False)
        if rebase.returncode != 0:
            run_git(repo, "rebase", "--abort", check=False)
            raise RuntimeError("publish: rebase conflict on a shared file; needs manual resolution")
    raise RuntimeError("publish: push failed after retries")

def pull(repo, remote="origin", branch="main"):
    """Session-start pull. Rebase local (unpushed) work on top of remote.
    Private/ is gitignored, so nothing local-only is touched."""
    run_git(repo, "fetch", remote, branch)
    run_git(repo, "rebase", f"{remote}/{branch}")
    return "pulled"
