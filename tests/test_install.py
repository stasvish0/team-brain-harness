import tools.install as install_mod
from tools.install import preflight, _is_github_ssh

def test_is_github_ssh():
    assert _is_github_ssh("git@github.com:acme/hive.git")
    assert not _is_github_ssh("/tmp/x/origin.git")
    assert not _is_github_ssh("https://github.com/acme/hive.git")

def test_preflight_flags_missing_git(monkeypatch):
    monkeypatch.setattr(install_mod.shutil, "which", lambda name: None)
    problems = preflight("/tmp/local/origin.git")
    assert any("git" in p for p in problems)

def test_preflight_skips_ssh_for_local_remote(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(install_mod, "ssh_ok",
                        lambda: called.__setitem__("n", called["n"] + 1) or True)
    preflight("/tmp/local/origin.git")
    assert called["n"] == 0

def test_preflight_checks_ssh_for_github_remote(monkeypatch):
    monkeypatch.setattr(install_mod, "ssh_ok", lambda: False)
    problems = preflight("git@github.com:acme/hive.git")
    assert any("SSH" in p or "ssh" in p for p in problems)
