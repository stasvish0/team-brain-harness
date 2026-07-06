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

def install(remote_url, dest, name, email, role):
    problems = preflight(remote_url)
    if problems:
        for p in problems:
            print("PREFLIGHT: " + p, file=sys.stderr)
        raise SystemExit(1)
    dest = Path(dest)
    setup_client(remote_url, dest, name=name, email=email)
    handle = slugify(email.split("@")[0])
    write_profile(dest, name, role, handle)
    print(f"Installed client at {dest}.")
    print(f"  identity: {name} <{email}>   handle: {handle}   role: {role}")
    print("Next: point your AI assistant at this directory and run /onboarding.")
    return dest

def _mirror(src, dst):
    """Copy src tree into dst, deleting files in dst not present in src. Ignores
    __pycache__ on both sides."""
    src, dst = Path(src), Path(dst)
    dst.mkdir(parents=True, exist_ok=True)
    def files(base):
        return {p.relative_to(base) for p in base.rglob("*")
                if p.is_file() and "__pycache__" not in p.parts}
    src_files = files(src)
    dst_files = files(dst)
    for rel in sorted(src_files):
        d = dst / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, d)
    for rel in sorted(dst_files - src_files):
        (dst / rel).unlink()

def update(dest):
    """Re-vendor only harness-owned client code; preserve all local state."""
    dest = Path(dest)
    _mirror(LIB, dest / "lib")
    _mirror(CLIENT_KIT / ".claude" / "hooks", dest / ".claude" / "hooks")
    shutil.copy2(CLIENT_KIT / ".claude" / "settings.local.json",
                 dest / ".claude" / "settings.local.json")
    shutil.copy2(CLIENT_KIT / "publish_allowlist.txt", dest / "publish_allowlist.txt")
    print(f"Updated client code at {dest} "
          "(private data, identity, and control-plane state preserved).")
    return dest

def _prompt_if_missing(value, label):
    if value:
        return value
    if sys.stdin.isatty():
        return input(f"{label}: ").strip()
    print(f"error: --{label} is required (stdin is not a TTY)", file=sys.stderr)
    raise SystemExit(2)
