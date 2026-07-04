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
    for raw in open(path):
        line = raw.split("#", 1)[0].strip()
        if line:
            lines.append(line)
    return lines
