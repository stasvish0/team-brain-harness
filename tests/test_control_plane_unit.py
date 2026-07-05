import json

import pytest

from lib.version import CLIENT_VERSION
from lib.control_plane import (
    version_tuple,
    read_manifest,
    read_applied,
    write_applied,
    DEFAULT_APPLIED,
    apply_migration,
    pending_migrations,
)


def test_client_version_is_a_dotted_string():
    assert isinstance(CLIENT_VERSION, str)
    assert version_tuple(CLIENT_VERSION)


def test_version_tuple_orders_correctly():
    assert version_tuple("0.0.1") < version_tuple("0.1.0")
    assert version_tuple("1.2.3") == version_tuple("1.2.3")
    assert version_tuple("0.10.0") > version_tuple("0.9.0")


def test_read_applied_defaults_when_missing(tmp_path):
    assert read_applied(tmp_path) == DEFAULT_APPLIED


def test_write_then_read_applied_roundtrips(tmp_path):
    applied = {"skills_version": 2, "structure_version": 3,
               "policy_version": 1, "announced_mcps": ["granola"]}
    write_applied(tmp_path, applied)
    assert read_applied(tmp_path) == applied


def test_read_manifest_reads_control_manifest(tmp_path):
    (tmp_path / "CONTROL").mkdir()
    (tmp_path / "CONTROL" / "manifest.json").write_text(
        json.dumps({"skills_version": 1, "structure_version": 0,
                    "min_client_version": "0.0.1", "required_mcps": [],
                    "policy_version": 1}))
    m = read_manifest(tmp_path)
    assert m["skills_version"] == 1 and m["min_client_version"] == "0.0.1"


def test_write_applied_is_atomic_on_crash(tmp_path, monkeypatch):
    good = {"skills_version": 1, "structure_version": 1,
            "policy_version": 1, "announced_mcps": []}
    write_applied(tmp_path, good)
    import lib.control_plane as cp
    monkeypatch.setattr(cp.os, "replace",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    try:
        write_applied(tmp_path, {"skills_version": 99})
    except OSError:
        pass
    assert read_applied(tmp_path) == good


def test_make_dir_and_keep_file_idempotent(tmp_path):
    mig = {"ops": [{"op": "make_dir", "path": "legal"},
                   {"op": "keep_file", "path": "legal/.gitkeep"}]}
    touched = apply_migration(tmp_path, mig)
    assert (tmp_path / "legal" / ".gitkeep").exists()
    assert "legal/.gitkeep" in touched
    assert apply_migration(tmp_path, mig) == set()


def test_move_quadrants(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "a" / "f.md").write_text("x\n")
    mig = {"ops": [{"op": "move", "from": "a/f.md", "to": "b/f.md"}]}
    touched = apply_migration(tmp_path, mig)
    assert not (tmp_path / "a" / "f.md").exists()
    assert (tmp_path / "b" / "f.md").exists()
    assert touched == {"a/f.md", "b/f.md"}
    assert apply_migration(tmp_path, mig) == set()


def test_move_collision_raises(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "a" / "f").write_text("1")
    (tmp_path / "b").mkdir(); (tmp_path / "b" / "f").write_text("2")
    with pytest.raises(ValueError):
        apply_migration(tmp_path, {"ops": [{"op": "move", "from": "a/f", "to": "b/f"}]})


def test_delete_idempotent(tmp_path):
    (tmp_path / "d").mkdir(); (tmp_path / "d" / "x").write_text("x")
    assert apply_migration(tmp_path, {"ops": [{"op": "delete", "path": "d/x"}]}) == {"d/x"}
    assert apply_migration(tmp_path, {"ops": [{"op": "delete", "path": "d/x"}]}) == set()


@pytest.mark.parametrize("bad", ["../escape", "/abs/path", "private/x", ".claude/x", ".git/x"])
def test_path_containment_rejected(tmp_path, bad):
    with pytest.raises(ValueError):
        apply_migration(tmp_path, {"ops": [{"op": "make_dir", "path": bad}]})


def test_pending_migrations_filters_and_sorts(tmp_path):
    md = tmp_path / "CONTROL" / "migrations"; md.mkdir(parents=True)
    (md / "0001-a.json").write_text('{"ops": []}')
    (md / "0002-b.json").write_text('{"ops": []}')
    (md / "0003-c.json").write_text('{"ops": []}')
    pend = pending_migrations(tmp_path, {"structure_version": 1})
    assert [p["id"] for p in pend] == [2, 3]


def test_pending_migrations_skips_misnamed(tmp_path):
    md = tmp_path / "CONTROL" / "migrations"; md.mkdir(parents=True)
    (md / "0001-a.json").write_text('{"ops": []}')
    (md / "notes.json").write_text('{"ops": []}')  # non-numeric prefix, skipped
    pend = pending_migrations(tmp_path, {"structure_version": 0})
    assert [p["id"] for p in pend] == [1]
