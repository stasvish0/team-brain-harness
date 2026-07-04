import subprocess, sys
from pathlib import Path
from lib.gitsync import run_git

ROOT = Path(__file__).resolve().parents[1]  # repo root, relative to tests/
PUBLISH_HOOK = ROOT / "client-kit" / ".claude" / "hooks" / "publish.py"

def _clone(bare, dest, email):
    subprocess.run(["git", "clone", str(bare), str(dest)], check=True)
    run_git(dest, "config", "user.email", email); run_git(dest, "config", "user.name", email)

def test_publish_hook_publishes(bare_remote, tmp_path):
    a = tmp_path / "a"; _clone(bare_remote, a, "a@x")
    (a / "engineering").mkdir(); (a / "engineering" / "n.md").write_text("x\n")
    allow = ROOT / "client-kit" / "publish_allowlist.txt"
    r = subprocess.run([sys.executable, str(PUBLISH_HOOK),
                        "--repo", str(a), "--allowlist", str(allow), "--message", "hook"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    c = tmp_path / "c"; subprocess.run(["git", "clone", str(bare_remote), str(c)], check=True)
    assert (c / "engineering" / "n.md").exists()
