import subprocess
from pathlib import Path

import tools.install as install_mod
from tools.install import preflight, _is_github_ssh, install, update
from lib.gitsync import run_git

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

def test_install_sets_identity_profile_and_working_client(bare_remote, tmp_path):
    dest = install(str(bare_remote), tmp_path / "c",
                   name="Ada", email="ada.lovelace@x.com", role="eng")
    assert run_git(dest, "config", "user.email").stdout.strip() == "ada.lovelace@x.com"
    prof = (dest / "private" / "personal-context" / "profile.md").read_text()
    assert "# Ada" in prof and "- role: eng" in prof
    assert "- handle: ada-lovelace" in prof
    assert (dest / ".claude" / "hooks" / "sync_pull.py").exists()

def test_install_prompt_fallback_errors_non_tty(monkeypatch):
    import tools.install as im
    monkeypatch.setattr(im.sys, "stdin",
                        type("S", (), {"isatty": staticmethod(lambda: False)})())
    import pytest
    with pytest.raises(SystemExit):
        im._prompt_if_missing("", "email")

def test_update_revendors_code_deletes_stale_preserves_local(bare_remote, tmp_path):
    dest = install(str(bare_remote), tmp_path / "c",
                   name="Ada", email="ada@x.com", role="eng")
    # a STALE lib file no longer in the harness
    (dest / "lib" / "stale_module.py").write_text("# old\n")
    # local state that MUST be preserved
    (dest / "private" / "personal-context" / "keep.md").write_text("mine\n")
    (dest / ".applied.json").write_text('{"skills_version": 7}\n')
    (dest / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
    (dest / ".claude" / "skills" / "materialized.md").write_text("from-control-plane\n")

    update(dest)

    assert not (dest / "lib" / "stale_module.py").exists()       # stale removed
    assert (dest / "lib" / "freshness.py").exists()              # real lib present
    assert (dest / "private" / "personal-context" / "keep.md").read_text() == "mine\n"
    assert (dest / ".applied.json").read_text() == '{"skills_version": 7}\n'
    assert (dest / ".claude" / "skills" / "materialized.md").read_text() == "from-control-plane\n"
    assert run_git(dest, "config", "user.email").stdout.strip() == "ada@x.com"
