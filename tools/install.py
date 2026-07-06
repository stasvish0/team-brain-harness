"""Member-facing installer for a team-brain-harness client. Stdlib only.
See docs/superpowers/specs/2026-07-06-installer-onboarding-design.md."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.meeting_rollup import slugify
from lib.profile import write_profile
from tools.setup_client import setup_client

LIB = ROOT / "lib"
CLIENT_KIT = ROOT / "client-kit"

def ssh_ok():
    """True if GitHub SSH authenticates. `ssh -T` exits non-zero even on success,
    so match the banner. BatchMode + accept-new guarantee no hang."""
    r = subprocess.run(
        ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
         "git@github.com"], capture_output=True, text=True)
    return "successfully authenticated" in (r.stderr or "")

def _is_github_ssh(url):
    return str(url).startswith("git@github.com:")

def preflight(remote_url):
    problems = []
    if shutil.which("git") is None:
        problems.append("git is not installed")
    if sys.version_info < (3, 11):
        problems.append("Python 3.11+ is required")
    if _is_github_ssh(remote_url) and not ssh_ok():
        problems.append(
            "GitHub SSH is not reachable. Generate a key:\n"
            "  ssh-keygen -t ed25519 -C \"your-email\"\n"
            "then paste ~/.ssh/id_ed25519.pub at https://github.com/settings/keys and re-run.")
    return problems
