#!/usr/bin/env python3
import argparse, sys
from pathlib import Path

def _repo_root(start):
    """Walk up from this file until we find the dir containing lib/gitsync.py.
    Works in both layouts, which put lib/ at different depths: the monorepo
    (client-kit/.claude/hooks/...) and a client clone (<clone>/.claude/hooks/...)."""
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / "lib" / "gitsync.py").exists():
            return cand
    raise RuntimeError("could not locate lib/gitsync.py above " + str(p))

sys.path.insert(0, str(_repo_root(__file__)))
from lib.gitsync import publish, read_allowlist

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--allowlist", required=True)
    ap.add_argument("--message", default="publish")
    a = ap.parse_args()
    result = publish(a.repo, a.message, read_allowlist(a.allowlist))
    print(result)

if __name__ == "__main__":
    main()
