#!/usr/bin/env python3
import argparse, sys
from pathlib import Path

def _repo_root(start):
    """Walk up from this file until we find the dir containing lib/gitsync.py
    (same helper as publish.py; works in both the monorepo and a client clone)."""
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / "lib" / "gitsync.py").exists():
            return cand
    raise RuntimeError("could not locate lib/gitsync.py above " + str(p))

sys.path.insert(0, str(_repo_root(__file__)))
from lib.gitsync import pull
from lib.meeting_rollup import roll_up_all

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    print(pull(a.repo))
    for name, status in roll_up_all(a.repo):
        print(f"rollup {name}: {status}")

if __name__ == "__main__":
    main()
