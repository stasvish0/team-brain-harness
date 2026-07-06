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
from lib.control_plane import apply_control_plane
from lib.meeting_rollup import roll_up_all
from lib.freshness import freshness_report

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    a = ap.parse_args()
    print(pull(a.repo))
    cp = apply_control_plane(a.repo)
    if cp["blocked"]:
        print("=== CONTROL PLANE: BLOCKED ===")
        for r in cp["gate_reasons"]:
            print(f"  - {r}")
        print("Update your client (re-run setup_client with the latest harness), then restart.")
        if cp["policy_text"]:
            print(cp["policy_text"])
        return
    if cp["migrations_applied"]:
        print(f"control: applied migrations {cp['migrations_applied']}")
    if cp["skills_changed"]:
        print(f"control: skills {cp['skills_changed']}")
    for m in cp["mcp_announcements"]:
        print(f"control: NEW MCP required: {m['name']} -> {m['how']}")
    if cp["policy_text"]:
        print(cp["policy_text"])
    for name, status in roll_up_all(a.repo):
        print(f"rollup {name}: {status}")
    from datetime import date
    for line in freshness_report(a.repo, date.today()):
        print(line)

if __name__ == "__main__":
    main()
