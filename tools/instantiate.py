import shutil
from pathlib import Path
from lib.gitsync import run_git

ROOT = Path(__file__).resolve().parents[1]
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
