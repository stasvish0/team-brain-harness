import json
import subprocess
from pathlib import Path
from lib.gitsync import run_git, push_paths, pull
from lib.meeting_rollup import roll_up, roll_up_all, parse_payload, SENTINEL
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


def _write_contrib(mdir, author, payload):
    inbox = mdir / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{author}.md").write_text(
        f"{SENTINEL}\n```json\n{json.dumps(payload)}\n```\n")

def _contrib_payload(author, decisions=None, notes=None):
    return {"meeting_id": "2026-07-04-standup", "title": "Daily Standup",
            "date": "2026-07-04", "author": author,
            "decisions": decisions or [], "action_items": [], "notes": notes or []}

def test_roll_up_merges_two_and_deletes_inbox(tmp_path):
    mdir = tmp_path / "meetings" / "2026-07-04-standup"
    _write_contrib(mdir, "alice", _contrib_payload("alice", decisions=["Ship it"]))
    _write_contrib(mdir, "bob", _contrib_payload("bob", notes=["Staging tight"]))
    changed = roll_up(tmp_path, mdir)
    assert changed is True
    canon = mdir / "standup.md"
    assert canon.exists()
    p = parse_payload(canon)
    assert p["decisions"] == [{"text": "Ship it", "by": ["alice"]}]
    assert p["notes"] == [{"text": "Staging tight", "by": ["bob"]}]
    assert not (mdir / "_inbox" / "alice.md").exists()
    assert not (mdir / "_inbox" / "bob.md").exists()

def test_roll_up_noop_when_no_inbox(tmp_path):
    mdir = tmp_path / "meetings" / "2026-07-04-standup"
    mdir.mkdir(parents=True)
    assert roll_up(tmp_path, mdir) is False

def test_roll_up_late_contribution_folds_and_is_idempotent(tmp_path):
    mdir = tmp_path / "meetings" / "2026-07-04-standup"
    _write_contrib(mdir, "alice", _contrib_payload("alice", decisions=["Ship it"]))
    assert roll_up(tmp_path, mdir) is True
    _write_contrib(mdir, "carol", _contrib_payload("carol", notes=["QA ok"]))
    assert roll_up(tmp_path, mdir) is True
    p = parse_payload(mdir / "standup.md")
    assert p["notes"] == [{"text": "QA ok", "by": ["carol"]}]
    assert len(p["merged_authors"]) == 2
    assert roll_up(tmp_path, mdir) is False  # no inbox left -> no-op

def test_roll_up_all_pushes_canonical_and_clears_inbox(bare_remote, tmp_path):
    a = _clone(bare_remote, tmp_path / "a")
    mdir = a / "meetings" / "2026-07-04-standup"
    _write_contrib(mdir, "alice", _contrib_payload("alice", decisions=["Ship it"]))
    _write_contrib(mdir, "bob", _contrib_payload("bob", notes=["Staging tight"]))
    push_paths(a, "inbox", ["meetings/"])  # contributions reach the remote tip

    b = _clone(bare_remote, tmp_path / "b")
    pull(b)  # exercises the fetch-before-rollup contract the reset invariant relies on
    results = roll_up_all(b)
    assert ("2026-07-04-standup", "pushed") in results

    c = _clone(bare_remote, tmp_path / "c")
    assert (c / "meetings" / "2026-07-04-standup" / "standup.md").exists()
    assert not (c / "meetings" / "2026-07-04-standup" / "_inbox").exists()
