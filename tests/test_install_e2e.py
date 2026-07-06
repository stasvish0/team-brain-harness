import subprocess, sys
from pathlib import Path
from tools.instantiate import instantiate
from tools.install import install, update
from lib.gitsync import run_git

def _bare_from(local, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote

def test_install_then_hook_runs_then_update(tmp_path):
    hive = instantiate(tmp_path / "hive")
    remote = _bare_from(hive, tmp_path)
    client = install(str(remote), tmp_path / "client",
                     name="Ada", email="ada@x.com", role="eng")

    r = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(client)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

    # the /onboarding skill reached the client via the CONTROL/skills mirror
    assert (client / ".claude" / "skills" / "onboarding" / "SKILL.md").exists()

    # update re-vendors code; the vendored version matches the harness
    update(client)
    harness_version = (Path(__file__).resolve().parents[1] / "lib" / "version.py").read_text()
    assert (client / "lib" / "version.py").read_text() == harness_version
