# ai-team-brain

A git-synced shared "team brain" for a group: a common knowledge tree that every
member syncs against, plus a private per-member tree that never leaves their machine.

## Product vs. live instance

This repository is the open-source **product** (installer/client-kit, hive-template,
tools, docs); it holds no group's data. A real group **instantiates a PRIVATE live
hive** from `hive-template` into its own private git repo, which is where the group's
actual shared knowledge lives. Members **sync against that private hive, never against
this public repo** - this repo only mints new hives and new member clones.

## Getting started

See **[docs/getting-started.md](docs/getting-started.md)** for the full
copy-pasteable walkthrough: create a hive (`python3 tools/instantiate.py <dest>`),
push it to a private GitHub repo, provision members
(`python3 tools/setup_client.py <remote-url> <dest>`), how the SessionStart pull and
explicit publish hooks work, and the golden rule that only allowlisted paths publish
while raw/private content never leaves.

## Design

The walking-skeleton design (git as the sync substrate, an allowlist as the primary
publish guard with gitignore as the backstop, and the pull/publish hook contract) is
what `lib/gitsync.py`, `tools/`, and `client-kit/` implement.

- Full design spec: [docs/superpowers/specs/2026-07-03-group-hive-brain-design.md](docs/superpowers/specs/2026-07-03-group-hive-brain-design.md)
- Implementation plan for this walking skeleton: [docs/superpowers/plans/2026-07-03-walking-skeleton-vault-and-hooks.md](docs/superpowers/plans/2026-07-03-walking-skeleton-vault-and-hooks.md)

The spec covers the full group system (control plane, meeting roll-up, TTL/freshness,
onboarding); this repo currently implements sub-project 1 (the vault + sync hooks).

## Development

```bash
python3 -m venv .venv
./.venv/bin/pip install pytest
./.venv/bin/python -m pytest -q
```

The venv is used because system Python is often PEP 668 externally-managed. See the
Development section of `docs/getting-started.md` for details.
