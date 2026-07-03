import subprocess
import pytest

def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args],
                          capture_output=True, text=True, check=True)

def init_identity(repo):
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")

@pytest.fixture
def bare_remote(tmp_path):
    """A bare repo standing in for GitHub, plus a seeded main branch."""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    seed = tmp_path / "seed"
    subprocess.run(["git", "clone", str(remote), str(seed)], check=True)
    init_identity(seed)
    (seed / "README.md").write_text("seed\n")
    _git(seed, "add", "-A"); _git(seed, "commit", "-m", "init")
    _git(seed, "push", "origin", "main")
    return remote
