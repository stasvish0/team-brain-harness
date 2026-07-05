"""Admin tool: scrub a path from all git history (leaked private data).
Rare and destructive. Dry-run by default; pass --force to execute."""
import os
import subprocess
import sys
from pathlib import Path

RUNBOOK = """
PURGE COMPLETE. Mandatory follow-up:
  1. Force-push the rewritten history:  git push --force --all && git push --force --tags
  2. Tell every member to re-clone (their old clones still contain the data).
  3. Rotate any exposed secret (assume it leaked).
Coordinate: announce the purge and confirm no one is mid-push before force-pushing.
"""

def _git(repo, *args, check=True):
    env = dict(os.environ, FILTER_BRANCH_SQUELCH_WARNING="1")
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=check, env=env)

def purge(repo, path, force=False):
    repo = Path(repo)
    if not force:
        print(f"[dry-run] would remove '{path}' from ALL history of {repo}")
        print("[dry-run] re-run with --force to execute.")
        print(RUNBOOK)
        return
    index_cmd = f"git rm -r --cached --ignore-unmatch {path}"
    _git(repo, "filter-branch", "--force", "--index-filter", index_cmd,
         "--prune-empty", "--tag-name-filter", "cat", "--", "--all")
    refs = _git(repo, "for-each-ref", "--format=%(refname)", "refs/original/",
                check=False).stdout.split()
    for ref in refs:
        _git(repo, "update-ref", "-d", ref, check=False)
    _git(repo, "reflog", "expire", "--expire=now", "--all", check=False)
    _git(repo, "gc", "--prune=now", "--aggressive", check=False)
    print(RUNBOOK)

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force"]
    if len(args) != 1:
        print("usage: python3 tools/purge.py <path> [--force]", file=sys.stderr)
        raise SystemExit(2)
    purge(Path.cwd(), args[0], force="--force" in sys.argv)
