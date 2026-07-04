import shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Allow running as a script (python3 tools/setup_client.py <remote-url> <dest>)
# from any cwd: ensure the repo root is importable so `lib.gitsync` resolves.
# Under pytest this is already on the path via pyproject's pythonpath=["."].
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.gitsync import run_git
CLIENT_KIT = ROOT / "client-kit"
LIB = ROOT / "lib"

PRIVATE_DIRS = ["personal-meetings", "personal-context", "personal-decisions",
                "personal-docs", "personal-drafts", "personal-projects", "personal-reviews"]

def setup_client(remote_url, dest):
    """Clone the live hive, vendor hooks + lib, and build the gitignored private tree.
    Minimal stand-in for the full installer (sub-project 5); no SSH/role handling."""
    dest = Path(dest)
    subprocess.run(["git", "clone", str(remote_url), str(dest)], check=True)
    run_git(dest, "config", "user.email", "member@example.com")
    run_git(dest, "config", "user.name", "Member")
    shutil.copytree(CLIENT_KIT / ".claude", dest / ".claude", dirs_exist_ok=True)
    shutil.copy2(CLIENT_KIT / "publish_allowlist.txt", dest / "publish_allowlist.txt")
    shutil.copytree(LIB, dest / "lib", dirs_exist_ok=True)
    for d in PRIVATE_DIRS:
        (dest / "private" / d).mkdir(parents=True, exist_ok=True)
    (dest / "private" / "TODO.md").write_text("# TODO\n")
    # Local-only ignores (.git/info/exclude), never touches the shared repo's
    # committed .gitignore. /private/ is ALSO ignored by the live hive's committed
    # .gitignore in production; listing it here is defense-in-depth and makes the
    # private tree ignored even when cloned from a plain remote.
    exclude = dest / ".git" / "info" / "exclude"
    exclude.write_text("/private/\n/lib/\n/.claude/\n/publish_allowlist.txt\n")
    return dest

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python3 tools/setup_client.py <remote-url> <dest>", file=sys.stderr)
        raise SystemExit(2)
    print(setup_client(sys.argv[1], sys.argv[2]))
