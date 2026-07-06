from lib.profile import write_profile


def test_write_profile_seeds_name_role_handle(tmp_path):
    p = write_profile(tmp_path, "Ada Lovelace", "eng", "ada")
    assert p == tmp_path / "private" / "personal-context" / "profile.md"
    text = p.read_text()
    assert "# Ada Lovelace" in text
    assert "- handle: ada" in text
    assert "- role: eng" in text
    assert "last_verified" not in text


def test_write_profile_idempotent(tmp_path):
    write_profile(tmp_path, "Ada", "eng", "ada")
    before = (tmp_path / "private" / "personal-context" / "profile.md").read_text()
    write_profile(tmp_path, "Ada", "eng", "ada")
    after = (tmp_path / "private" / "personal-context" / "profile.md").read_text()
    assert before == after
