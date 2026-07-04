from pathlib import Path

TEMPLATE = Path.home() / "ai-team-brain" / "hive-template"

def test_functional_dirs_exist():
    for d in ["org", "product", "engineering", "design", "customers",
              "market", "knowledge", "projects", "decisions", "meetings", "CONTROL"]:
        assert (TEMPLATE / d).is_dir(), f"missing {d}"

def test_gitignore_blocks_private_and_local_skills():
    text = (TEMPLATE / ".gitignore").read_text()
    assert "/private/" in text
    assert ".claude/skills-local/" in text
