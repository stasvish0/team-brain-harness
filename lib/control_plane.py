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
