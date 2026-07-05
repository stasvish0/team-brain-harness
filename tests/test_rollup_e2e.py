import subprocess, sys, json
from pathlib import Path
from tools.instantiate import instantiate
from tools.setup_client import setup_client
from lib.gitsync import run_git
from lib.meeting_rollup import SENTINEL

ROOT = Path(__file__).resolve().parents[1]


def _bare_from(local, tmp_path):
    remote = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True)
    run_git(local, "remote", "add", "origin", str(remote))
    run_git(local, "push", "origin", "main")
    return remote


def _inbox_file(client, author, payload):
    mdir = client / "meetings" / "2026-07-04-standup" / "_inbox"
    mdir.mkdir(parents=True, exist_ok=True)
    (mdir / f"{author}.md").write_text(
        f"{SENTINEL}\n```json\n{json.dumps(payload)}\n```\n")


def _publish(client):
    r = subprocess.run(
        [sys.executable, str(client / ".claude" / "hooks" / "publish.py"),
         "--repo", str(client), "--allowlist", str(client / "publish_allowlist.txt"),
         "--message", "inbox"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_meeting_rollup_end_to_end(tmp_path):
    hive = instantiate(tmp_path / "acme-hive")
    remote = _bare_from(hive, tmp_path)
    alice = setup_client(str(remote), tmp_path / "alice")
    bob = setup_client(str(remote), tmp_path / "bob")
    carol = setup_client(str(remote), tmp_path / "carol")

    # raw transcripts stay private
    (alice / "private" / "personal-meetings" / "raw.md").write_text("alice raw secret\n")
    (bob / "private" / "personal-meetings" / "raw.md").write_text("bob raw secret\n")

    def payload(who, **kw):
        return {"meeting_id": "2026-07-04-standup", "title": "Daily Standup",
                "date": "2026-07-04", "author": who,
                "decisions": kw.get("d", []), "action_items": [], "notes": kw.get("n", [])}

    _inbox_file(alice, "alice", payload("alice", d=["Ship v2 behind a flag"]))
    assert _publish(alice) == "pushed"
    _inbox_file(bob, "bob", payload("bob", n=["Staging is tight"]))
    assert _publish(bob) == "pushed"  # fetch-rebase-retry catches up to alice

    # carol's session start: pull + roll up
    r = subprocess.run(
        [sys.executable, str(carol / ".claude" / "hooks" / "sync_pull.py"),
         "--repo", str(carol)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "rollup 2026-07-04-standup: pushed" in r.stdout

    # verify on a fresh clone of the remote
    verify = tmp_path / "verify"
    subprocess.run(["git", "clone", str(remote), str(verify)], check=True)
    canon = verify / "meetings" / "2026-07-04-standup" / "standup.md"
    assert canon.exists()
    text = canon.read_text()
    assert "Ship v2 behind a flag" in text
    assert "Staging is tight" in text
    assert not (verify / "meetings" / "2026-07-04-standup" / "_inbox").exists()
    # no raw transcript ever left
    assert not (verify / "private").exists()
    assert "raw secret" not in text
