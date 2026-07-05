import json

from lib.version import CLIENT_VERSION
from lib.control_plane import (
    version_tuple,
    read_manifest,
    read_applied,
    write_applied,
    DEFAULT_APPLIED,
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
