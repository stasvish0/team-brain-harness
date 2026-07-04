import subprocess
from pathlib import Path
from lib.gitsync import run_git, push_paths
from tests.conftest import init_identity  # reuse identity helper


def _clone(remote, dest):
    subprocess.run(["git", "clone", str(remote), str(dest)], check=True)
    init_identity(dest)
    return dest


def test_push_paths_stages_including_deletions(bare_remote, tmp_path):
    a = _clone(bare_remote, tmp_path / "a")
    mdir = a / "meetings" / "2026-07-04-standup"
    (mdir / "_inbox").mkdir(parents=True)
    (mdir / "_inbox" / "alice.md").write_text("x\n")
    assert push_paths(a, "add inbox", ["meetings/"]) == "pushed"

    # delete the inbox file and add a canonical note; push via directory pathspec
    (mdir / "_inbox" / "alice.md").unlink()
    (mdir / "standup.md").write_text("canonical\n")
    assert push_paths(a, "roll up", ["meetings/"]) == "pushed"

    # a fresh clone must NOT contain the deleted inbox file
    b = _clone(bare_remote, tmp_path / "b")
    assert (b / "meetings" / "2026-07-04-standup" / "standup.md").exists()
    assert not (b / "meetings" / "2026-07-04-standup" / "_inbox" / "alice.md").exists()


def test_push_paths_nothing_to_publish(bare_remote, tmp_path):
    a = _clone(bare_remote, tmp_path / "a")
    assert push_paths(a, "noop", ["meetings/"]) == "nothing-to-publish"
