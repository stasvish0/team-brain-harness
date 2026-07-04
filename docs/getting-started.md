# Getting started

This is a copy-pasteable walkthrough for standing up a group "team brain" and
provisioning members against it.

## What this repo is (product vs. live instance)

This repository is the **open-source product**, not anyone's data. It ships four things:

- **installer / client-kit** (`client-kit/`) - the hooks, allowlist, and per-member
  scaffolding that a member's clone gets.
- **hive-template** (`hive-template/`) - the empty knowledge tree a group starts from.
- **tools** (`tools/`) - `instantiate.py` (create a live hive) and `setup_client.py`
  (provision a member).
- **library + docs** (`lib/`, `docs/`) - the git-sync engine and this guide.

The product-vs-live-instance model:

- A real group **instantiates a PRIVATE live hive** from `hive-template`. That private
  hive is a separate git repo (typically a private GitHub repo) and holds the group's
  actual shared knowledge.
- **Members sync against that private hive**, never against this public product repo.
- This public repo only produces new hives and new member clones; it never receives
  anyone's content.

```
this public repo  --instantiate-->  PRIVATE live hive (private GitHub repo)
                                          ^          ^
                                          |          |
                                   member A     member B   (clones, sync here)
```

## 1. Create a live hive

`instantiate` copies `hive-template`, vendors the CONTROL skills, and makes the first
commit. It exposes an `instantiate(dest)` function and a tiny CLI.

Using the CLI (the dest path is `argv[1]`):

```bash
python3 tools/instantiate.py /path/to/acme-hive
```

Equivalent, calling the function directly:

```bash
python3 -c "from tools.instantiate import instantiate; instantiate('/path/to/acme-hive')"
```

Either one prints the created path and leaves a git repo with one commit
(`chore: instantiate live hive from template`).

Now push it to a **new private GitHub repo** (create the empty repo first, then):

```bash
cd /path/to/acme-hive
git remote add origin git@github.com:acme/acme-hive.git   # your PRIVATE repo
git push -u origin main
```

That remote URL is what members sync against below.

## 2. Provision a member

`setup_client` clones the live hive, vendors the hooks + `lib/`, and builds the
gitignored `private/` tree. It exposes a `setup_client(remote_url, dest)` function and
a CLI.

Using the CLI (`argv[1]` is the remote URL, `argv[2]` is the dest):

```bash
python3 tools/setup_client.py git@github.com:acme/acme-hive.git /path/to/alice
```

Equivalent, calling the function directly:

```bash
python3 -c "from tools.setup_client import setup_client; setup_client('git@github.com:acme/acme-hive.git', '/path/to/alice')"
```

The member clone contains the shared tree (`engineering/`, `decisions/`, ...), the
member's own gitignored `private/` tree, the two hooks under `.claude/hooks/`, a
`publish_allowlist.txt`, and a vendored `lib/`.

## 3. How the two hooks work

Members never run raw git for sync. Two hooks handle it:

- **SessionStart pull** (`.claude/hooks/sync_pull.py`) - runs on session start and
  fetches + rebases the member's clone onto the live hive so they open with the
  latest shared knowledge. Wired in `client-kit/.claude/settings.local.json` and
  invoked as `python3 .claude/hooks/sync_pull.py --repo <clone>`.

- **Explicit publish** (`.claude/hooks/publish.py`) - run when a member wants to push
  shared changes upstream. It stages only allowlisted paths, commits, and pushes with
  fetch->rebase->retry so a concurrent push is never clobbered:

  ```bash
  python3 .claude/hooks/publish.py \
    --repo /path/to/alice \
    --allowlist /path/to/alice/publish_allowlist.txt \
    --message "add adr-001"
  ```

  It prints `pushed` when something went up, or `nothing-to-publish` when there was
  nothing staged after applying the allowlist.

## 4. The private tree and the golden rule

Every member clone has a `private/` tree (`private/personal-context/`,
`private/personal-meetings/`, `private/TODO.md`, ...). This is the member's own raw and
personal content.

**Golden rule: only allowlisted paths publish, and raw/private content never leaves.**

Two layers enforce it:

- **The allowlist is the primary guard.** `publish` stages *only* the pathspecs listed
  in `publish_allowlist.txt` (`org/`, `engineering/`, `decisions/`, `CONTROL/`, ...).
  A file outside those paths is never staged, so it is never committed or pushed.
- **gitignore is the backstop.** `/private/` is gitignored both by the live hive's
  committed `.gitignore` and by each clone's local `.git/info/exclude`, so even a stray
  `git add` cannot stage it.

The result: a member can keep personal notes in `private/` forever and they will never
reach the shared remote. This is exercised end to end by
`tests/test_e2e_loop.py`, which writes a private note and a shared note, publishes, and
asserts the private note never reaches the remote.

## Development

The repo uses **pytest**. Set up an isolated virtualenv and run the suite:

```bash
python3 -m venv .venv
./.venv/bin/pip install pytest
./.venv/bin/python -m pytest -q
```

Why the venv: on many modern systems the system Python is **PEP 668
externally-managed**, so `pip install` into it is blocked (and polluting system Python
is a bad idea anyway). A local `.venv` sidesteps that and keeps the toolchain
reproducible. `pyproject.toml` sets `pythonpath = ["."]` so tests import `lib`,
`tools`, etc. without any install step.
