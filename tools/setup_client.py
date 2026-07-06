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

def setup_client(remote_url, dest, name="Member", email="member@example.com"):
    """Clone the live hive, vendor hooks + lib, and build the gitignored private tree.
    Minimal stand-in for the full installer (sub-project 5); no SSH/role handling."""
    dest = Path(dest)
    subprocess.run(["git", "clone", str(remote_url), str(dest)], check=True)
    run_git(dest, "config", "user.email", email)
    run_git(dest, "config", "user.name", name)
    shutil.copytree(CLIENT_KIT / ".claude", dest / ".claude", dirs_exist_ok=True)
    shutil.copy2(CLIENT_KIT / "publish_allowlist.txt", dest / "publish_allowlist.txt")
    shutil.copytree(LIB, dest / "lib", dirs_exist_ok=True)
    # Materialize the shared skills mirror and seed control-plane bookkeeping so a
    # fresh client starts current (the clone already carries the post-migration tree).
    # A real hive always ships CONTROL/manifest.json; guard for manifest-less clones.
    if (dest / "CONTROL" / "manifest.json").is_file():
        if str(dest) not in sys.path:
            sys.path.insert(0, str(dest))
        from lib.control_plane import sync_skills, read_manifest, write_applied, _migration_id
        sync_skills(dest)
        manifest = read_manifest(dest)
        migs = sorted((dest / "CONTROL" / "migrations").glob("*.json")) \
            if (dest / "CONTROL" / "migrations").is_dir() else []
        mig_ids = [i for i in (_migration_id(p) for p in migs) if i is not None]
        structure_version = max(mig_ids, default=0)
        write_applied(dest, {
            "skills_version": manifest.get("skills_version", 0),
            "structure_version": structure_version,
            "policy_version": manifest.get("policy_version", 0),
            "announced_mcps": [m["name"] for m in manifest.get("required_mcps", [])],
        })
    for d in PRIVATE_DIRS:
        (dest / "private" / d).mkdir(parents=True, exist_ok=True)
    (dest / "private" / "TODO.md").write_text("# TODO\n")
    # Local-only ignores (.git/info/exclude), never touches the shared repo's
    # committed .gitignore. /private/ is ALSO ignored by the live hive's committed
    # .gitignore in production; listing it here is defense-in-depth and makes the
    # private tree ignored even when cloned from a plain remote.
    exclude = dest / ".git" / "info" / "exclude"
    exclude.write_text("/private/\n/lib/\n/.claude/\n/publish_allowlist.txt\n"
                       "/.applied.json\n/.control-block\n")
    return dest

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: python3 tools/setup_client.py <remote-url> <dest>", file=sys.stderr)
        raise SystemExit(2)
    print(setup_client(sys.argv[1], sys.argv[2]))
