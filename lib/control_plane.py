"""Client-side control plane: reconcile a client against CONTROL/manifest.json
on session start. Stdlib only. See
docs/superpowers/specs/2026-07-05-control-plane-design.md."""
import json
import os
import shutil
from pathlib import Path


def version_tuple(s):
    """Parse a dotted version like '0.0.1' into a comparable tuple of ints."""
    return tuple(int(x) for x in str(s).split("."))


DEFAULT_APPLIED = {"skills_version": 0, "structure_version": 0,
                   "policy_version": 0, "announced_mcps": []}


def read_manifest(repo):
    return json.loads((Path(repo) / "CONTROL" / "manifest.json").read_text())


def read_applied(repo):
    p = Path(repo) / ".applied.json"
    if not p.exists():
        return dict(DEFAULT_APPLIED)
    return json.loads(p.read_text())


def _atomic_write(path, text):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def write_applied(repo, applied):
    _atomic_write(Path(repo) / ".applied.json",
                  json.dumps(applied, indent=2, sort_keys=True) + "\n")
