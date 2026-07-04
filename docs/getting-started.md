# Getting started

A step-by-step, copy-pasteable guide to standing up a team brain and joining it. Follow the part that matches you:

- **[Part A: Admin](#part-a-admin--create-the-team-brain-once)** creates the shared brain once.
- **[Part B: Member](#part-b-member--join-the-team-brain)** joins it on their machine.
- **[Part C: Daily use](#part-c-daily-use)** is what everyone does day to day.

> This repo is the open-source **product**, not anyone's data. You will create a separate **private live hive** from it and sync against that. See [Product vs. live instance](../README.md#product-vs-live-instance).

---

## Prerequisites

You need three things. Check them first:

```bash
git --version        # any recent git
python3 --version    # 3.11 or newer
ssh -T git@github.com   # should greet you by username (SSH set up with GitHub)
```

If `ssh -T git@github.com` fails, add an SSH key to your GitHub account first: [GitHub's SSH guide](https://docs.github.com/en/authentication/connecting-to-github-with-ssh). This is the one manual step for non-technical members; an admin can walk you through it.

Then get this harness on your machine:

```bash
git clone git@github.com:YOUR_ORG/team-brain-harness.git
cd team-brain-harness
```

---

## Part A: Admin, create the team brain (once)

You will create a live hive from the template and push it to a **new private** GitHub repo. Members sync against that repo.

**Step 1. Instantiate a live hive locally.**

```bash
python3 tools/instantiate.py ~/acme-hive
```

This copies the empty vault scaffolding, vendors the shared skills into `CONTROL/`, and makes the first commit. It prints the path and leaves a git repo with one commit.

**Step 2. Create an empty PRIVATE repo on GitHub.** Either in the GitHub UI (New repository, Private, no README), or with the CLI:

```bash
gh repo create ACME/acme-hive --private
```

**Step 3. Push the hive to it.**

```bash
cd ~/acme-hive
git remote add origin git@github.com:ACME/acme-hive.git
git push -u origin main
```

**Step 4. Share the remote URL** (`git@github.com:ACME/acme-hive.git`) with your team. That is the only thing members need from you.

Done. The team brain exists. Everything members add flows into this repo.

---

## Part B: Member, join the team brain

One command provisions your local client from the hive URL your admin gave you:

```bash
python3 tools/setup_client.py git@github.com:ACME/acme-hive.git ~/acme-brain
```

This clones the hive, vendors the sync hooks and the git-sync library, and builds your private tree. You now have:

```text
~/acme-brain/                 # your clone of the shared team brain (syncs)
├─ engineering/  product/  design/  customers/  market/  ...   # shared knowledge
├─ CONTROL/                   # shared skills + manifest
├─ .claude/
│  ├─ hooks/                  # sync_pull.py + publish.py (run for you)
│  └─ settings.local.json     # wires the SessionStart pull
├─ publish_allowlist.txt      # which paths may be published
└─ private/                   # LOCAL ONLY, never leaves your machine
   ├─ personal-meetings/      #   raw transcripts live here
   ├─ personal-context/  personal-decisions/  personal-docs/
   ├─ personal-drafts/   personal-projects/   personal-reviews/
   └─ TODO.md
```

Point your AI assistant (e.g. Claude Code) at `~/acme-brain` and you are ready.

---

## Part C: Daily use

**Pull happens automatically.** When your assistant starts a session in `~/acme-brain`, the SessionStart hook runs `git pull` so you open already caught up on the team's latest shared knowledge. To pull manually:

```bash
python3 .claude/hooks/sync_pull.py --repo ~/acme-brain
```

**Publish when you have something to share.** Publishing is always explicit. It stages only allowlisted shared paths, commits, and pushes with fetch-rebase-retry so a teammate's concurrent push is never clobbered:

```bash
python3 .claude/hooks/publish.py \
  --repo ~/acme-brain \
  --allowlist ~/acme-brain/publish_allowlist.txt \
  --message "standup notes 2026-07-04"
```

It prints `pushed` when something went up, or `nothing-to-publish` when nothing allowlisted had changed.

**The golden rule:** only allowlisted paths publish, and raw/private content never leaves. Keep raw transcripts and personal notes in `private/`; put anything meant for the team in the shared folders (`engineering/`, `product/`, `decisions/`, ...).

**Process a meeting into a shared record.** After a meeting whose raw transcript you saved under `private/personal-meetings/`, run the `/process-meeting` skill in your assistant. It summarizes your transcript into a structured contribution (decisions, action items, notes), writes it to `meetings/<id>/_inbox/<you>.md`, and publishes it. The raw transcript never leaves your machine; only the summary is shared. You do not merge by hand: the next teammate's session-start hook automatically rolls up every attendee's contribution into one canonical note (`meetings/<id>/<slug>.md`), deletes the inbox, and pushes. Re-runs and late contributions fold into the same note, deterministically.

### What a standup looks like

```mermaid
sequenceDiagram
  participant You as You (local)
  participant H as Team brain (git)
  Note over You: Record raw standup notes into private/personal-meetings/ (stays local)
  You->>You: process them into shareable notes (decisions, action items)
  You->>You: write those into a shared folder, e.g. meetings/ or projects/
  You->>H: publish.py  (allowlisted paths only, rebase+retry)
  Note over H: Your teammate publishes too; both land, nothing overwritten
  H->>You: next session start: sync_pull.py
  Note over You: Your assistant now knows the whole standup, raw recording never left your machine
```

---

## Command reference

| Goal | Command |
|------|---------|
| Create a live hive | `python3 tools/instantiate.py <dest>` |
| Provision a member client | `python3 tools/setup_client.py <hive-git-url> <dest>` |
| Pull latest (manual) | `python3 .claude/hooks/sync_pull.py --repo <clone>` |
| Publish shared changes | `python3 .claude/hooks/publish.py --repo <clone> --allowlist <clone>/publish_allowlist.txt --message "..."` |
| Process a meeting into a shared contribution | run the `/process-meeting` skill in your assistant |
| Run the test suite | `./.venv/bin/python -m pytest -q` |

The two tools also expose plain functions if you prefer: `from tools.instantiate import instantiate` and `from tools.setup_client import setup_client`.

---

## Development

The repo uses **pytest**. Set up an isolated virtualenv and run the suite:

```bash
python3 -m venv .venv
./.venv/bin/pip install pytest
./.venv/bin/python -m pytest -q
```

Why the venv: on many modern systems the system Python is **PEP 668 externally-managed**, so `pip install` into it is blocked. A local `.venv` sidesteps that. `pyproject.toml` sets `pythonpath = ["."]` so tests import `lib`, `tools`, etc. with no install step. The suite exercises real git behavior against temporary repositories, including the end-to-end publish/pull loop and the privacy invariant.

---

## Troubleshooting

- **`ssh -T git@github.com` fails / push is denied.** Your SSH key is not registered with GitHub. Follow the SSH guide linked in Prerequisites, then retry.
- **`pip install` refused with an "externally-managed-environment" error.** Use the `.venv` steps in Development; do not install into system Python.
- **`publish.py` prints `nothing-to-publish`.** Nothing under the allowlisted paths changed. Make sure your shared content is in a folder listed in `publish_allowlist.txt` (not in `private/`).
- **A publish raised a rebase-conflict error.** Two people edited the same shared file at once. That is intentionally routed to a human: pull, resolve the file, and publish again. Your repo is left clean (not mid-rebase).
