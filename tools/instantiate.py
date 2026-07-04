import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Allow running as a script (python3 tools/instantiate.py <dest>) from any cwd:
# ensure the repo root is importable so `lib.gitsync` resolves. Under pytest this
# is already on the path via pyproject's pythonpath=["."], so this is a no-op there.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.gitsync import run_git
TEMPLATE = ROOT / "hive-template"
CLIENT_SKILLS = ROOT / "client-kit" / "skills"

def instantiate(dest):
    """Create a new live-hive git repo from hive-template, vendoring CONTROL skills."""
    dest = Path(dest)
    shutil.copytree(TEMPLATE, dest)
    (dest / "CONTROL" / "skills").mkdir(parents=True, exist_ok=True)
    if CLIENT_SKILLS.exists():
        shutil.copytree(CLIENT_SKILLS, dest / "CONTROL" / "skills", dirs_exist_ok=True)
    run_git(dest, "init", "-b", "main")
    run_git(dest, "config", "user.email", "hive@example.com")
    run_git(dest, "config", "user.name", "Hive Bootstrap")
    run_git(dest, "add", "-A")
    run_git(dest, "commit", "-m", "chore: instantiate live hive from template")
    return dest

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 tools/instantiate.py <dest>", file=sys.stderr)
        raise SystemExit(2)
    print(instantiate(sys.argv[1]))
