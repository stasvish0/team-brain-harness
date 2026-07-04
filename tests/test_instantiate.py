import subprocess
from pathlib import Path
from tools.instantiate import instantiate

def test_instantiate_creates_committed_hive(tmp_path):
    dest = tmp_path / "acme-hive"
    instantiate(dest)
    assert (dest / "CONTROL" / "manifest.json").is_file()
    assert (dest / "engineering").is_dir()
    log = subprocess.run(["git", "-C", str(dest), "log", "--oneline"],
                         capture_output=True, text=True, check=True)
    assert len(log.stdout.strip().splitlines()) == 1
    assert (dest / "CONTROL" / "skills").is_dir()
