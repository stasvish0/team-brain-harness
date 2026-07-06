"""Seed a member's minimal personal-context profile. Stdlib only.
See docs/superpowers/specs/2026-07-06-installer-onboarding-design.md."""
import os
from pathlib import Path


def write_profile(dest, name, role, handle):
    """Write <dest>/private/personal-context/profile.md atomically. Minimal seed;
    the /onboarding skill enriches the prose but leaves handle/role lines intact.
    No last_verified front-matter (so freshness never flags a member's own profile)."""
    d = Path(dest) / "private" / "personal-context"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "profile.md"
    content = (f"# {name}\n\n"
               f"- handle: {handle}\n"
               f"- role: {role}\n\n"
               "(Run /onboarding to add your primary domain, current focus, and what you work on.)\n")
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text(content)
    os.replace(tmp, p)
    return p
