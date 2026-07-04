# Group Hive Brain: a shared team brain for a cross-functional group

- **Date:** 2026-07-03
- **Status:** Draft for review
- **Author:** team-brain-harness maintainers
- **Builds on:** a single-user personal-knowledge OS pattern (a per-person AI assistant with skills, a memory/freshness subsystem, and a folder taxonomy)

---

## 1. Context and goals

The single-user pattern this builds on is a markdown-based personal operating system for one person, run inside a local AI client, with skills, a memory/freshness subsystem, and a folder taxonomy. This spec extends that model to a **cross-functional product group**: a shared "hive brain" of context that many people (engineers, PMs, UX, support, sales) contribute to and read from, each through their own local AI assistant.

Goals:
- A single shared vault of group context that every member's assistant reads and writes.
- Each member runs a local assistant seeded from a starter kit; hooks sync context up and down automatically.
- A central control plane so the admin can push new skills, directory-structure changes, and new MCPs to every client.
- Strong, structural privacy: personal and sensitive material never lands centrally.
- An admin who can prune the vault and purge anything that leaks in.

**Primary deliverable and delivery sequence.** The main artifact is the **open-source monorepo** itself: a complete, documented, reusable setup anyone could clone and stand up. Deployment to a real group is **not** part of building the artifact; it is the *first use* of the finished artifact and its validation (dogfooding as the first deployment). Sequence: (1) build the monorepo across the sub-projects, (2) then instantiate a private live hive for the group from that repo.

**Acceptance gate (dogfood):** the artifact is "done" only when a maintainer can stand up a group's live hive and onboard members using **only the repo's own getting-started and how-to docs**, with no undocumented steps. This forces the installer and docs to be genuinely complete rather than dependent on tribal knowledge.

Design bias: keep it simple and grounded by a concrete first deployment, while staying general enough to be a clean open-source project (no company specifics baked into the repo).

## 2. Non-goals and constraints

- Not building a bespoke server, broker, or SSO integration for v1. Rejected as too complex.
- Not real-time collaborative editing.
- Not role-based access limiting. Cross-functional collaboration is explicitly valued (see 3.7).
- The new company's exact tool stack is not yet known; MCP wiring is deferred to onboarding.
- No em dashes or en dashes in generated content (house style).

## 3. Key decisions

### 3.1 Backbone: Git on GitHub, packaged as one open-source monorepo
Git/GitHub is the backbone: a versioned control plane, a free audit trail, offline-first operation, and PR-as-publish-gate. Purging leaked data needs history rewrite, acceptable because private-by-default makes leaks rare.

Everything ships as a **single open-source monorepo** (installer, client kit, hive template, control-plane tooling, and all documentation) so anyone can clone it and walk through setup.

**Product vs. live instance (important):** the monorepo is the open-source *product* (source, tooling, docs, and an empty `hive-template/`). A real group *instantiates* a private **live hive** repo from `hive-template/`, with `CONTROL/` vendored in; members' clients sync against that private live hive, never the public monorepo. This keeps company content out of the open-source repo and lets a deployment pull tooling upgrades by re-vendoring from the monorepo. See 4.10 for the topology.

### 3.2 Auth: personal GitHub accounts + SSH keys
Every member has their own GitHub account and an SSH key. No SSO, no broker, no token-provisioning service. The admin personally teaches non-technical members how to create an account and register their key. A bootstrap installer automates the machine side: it generates the SSH keypair, prints the public key and opens the GitHub SSH-keys page for the user to paste it (the only manual step, which the admin assists with), then configures git so users never run raw git commands.

### 3.3 Privacy: private by default, explicit publish
Nothing leaves a client unless it sits in a designated shared area (the repo working tree, minus gitignored paths). Personal content lives in a local, gitignored `private/` tree that the sync hooks never touch. Publishing is an explicit act that stages an allowlist of shared paths.

### 3.4 Concurrency and roll-up
Git rejects non-fast-forward pushes, so no client can silently overwrite another's commit. The upstream hook does `fetch -> rebase -> push` with retry on rejection. Content that multiple people can produce for the same artifact (for example a processed meeting note) is first written to an **ephemeral, author-namespaced inbox** (`meetings/<id>/_inbox/<author>.md`) so concurrent writes touch different files and merge trivially. A roll-up then merges the inbox into a **single canonical note** and deletes the inbox. Per-author files are transient plumbing, never persisted.

### 3.5 Roll-up execution: opportunistic client (no CI)
The next client to sync (the next session-start pull by any member) notices a pending `_inbox/`, merges it into the canonical note, deletes the inbox, and pushes. No GitHub Actions, no server. Tradeoff accepted: during quiet periods the canonical note lags and a reader may briefly see loose inbox files.

**Trigger (definition):** roll-up fires on the mere presence of unmerged contributions in an `_inbox/`, detected during the session-start pull, not on a time-based staleness window. "Unmerged" means the inbox holds contributions not yet reflected in the canonical note. It is idempotent, so re-running is safe and late contributions fold into the same note.

### 3.6 Control plane: git-native manifest, auto-apply safe / gate breaking
The admin edits `CONTROL/` and pushes; there is no separate push-to-clients channel. Each client, on its next session-start pull, compares `CONTROL/manifest.json` against a local `.applied.json` and reconciles. Enforcement policy: skills and additive migrations apply silently; breaking structure migrations and `min_client_version` bumps gate the session until resolved; new MCPs are announced with setup instructions (auth needs a human); `policy.md` is reloaded as standing instructions.

### 3.7 Access: one repo, universal read/write; roles are affinity, not limits
Single repo, every member can read and write every directory. GitHub read access is per-repo (not per-folder), so a single repo means universal read by design, which matches the cross-functional goal. Roles are a **soft profile** (stored in `personal-context`) that gives the assistant emphasis (relevant skills first, primary domain, a default publish location) but never restricts. Anyone can run any skill and write anywhere. A restricted second repo can be added later if some data becomes genuinely need-to-know.

## 4. Architecture

### 4.1 Central vault (the repo)
```
group-vault/                 # the GitHub repo = the hive brain
├─ CONTROL/                  # control plane (admin-owned)
│  ├─ manifest.json          #   skills_version, structure_version,
│  │                         #   min_client_version, required_mcps[], policy_version
│  ├─ skills/                #   canonical shared skills, synced to clients
│  ├─ migrations/            #   dated, ordered, idempotent structure changes
│  ├─ roles.json             #   role -> suggested emphasis (NOT an allowlist)
│  └─ policy.md              #   standing instructions loaded into every assistant
├─ org/                      # people (shared facts), teams, roster
├─ product/                  # roadmap, PRDs, priorities
├─ engineering/              # teams, architecture, decisions (ADRs)
├─ design/                   # UX research, flows, specs
├─ customers/                # accounts, feedback, support themes
├─ market/                   # competitors, positioning, deals
├─ knowledge/                # shared knowledge domains (second brain)
├─ projects/  decisions/  meetings/   # cross-cutting shared records
└─ .gitignore                # ignores private/ and skills-local/
```

### 4.2 Client machine
```
~/hive/                      # git clone (SHARED, syncs)
├─ .claude/
│  ├─ skills/                #   shared skills (from CONTROL, tracked)
│  ├─ skills-local/          #   personal skills (gitignored, never sync)
│  └─ hooks/                 #   the two sync hooks
├─ CONTROL/ org/ product/ ...#   shared context (tracked)
├─ .applied.json             #   local record of applied control-plane versions
└─ .gitignore

~/hive/private/              # gitignored, LOCAL ONLY, never synced
├─ personal-meetings/        #   raw transcripts (raw never leaves)
├─ personal-context/         #   role/profile, what I work on
├─ personal-decisions/
├─ personal-docs/
├─ personal-drafts/
├─ personal-projects/
├─ personal-reviews/
└─ TODO.md                   #   target of a private /todo skill
```
The assistant reads shared + private together and loads shared + local skills together. Only the tracked, non-ignored tree ever leaves the machine.

### 4.3 Sync engine (two hooks)
**SessionStart -> pull and catch up:**
1. `git pull` latest shared context.
2. Apply the control plane (see 4.5).
3. Run the TTL / freshness check (see 4.7).
4. If any `_inbox/` holds contributions not yet reflected in its canonical note, roll it up (see 4.4).

**Publish -> push (session end / on demand):**
1. Process private drafts into shareable output.
2. Stage only an allowlist of shared paths (never `git add -A`).
3. `fetch -> rebase -> push`, retry on rejection with backoff.

### 4.4 Concurrency and roll-up
- Author-namespaced ephemeral inbox for multi-writer artifacts.
- Opportunistic client roll-up: next session-start pull merges the inbox into one canonical note (merge unions decisions and dedupes action items, keeps attribution inline), deletes the inbox, pushes. Idempotent, so late contributions fold into the same note.
- **Canonical note format (the load-bearing contract for the merge):** one markdown file per meeting with fixed sections in fixed order: `## Decisions`, `## Action items` (grouped by owner), `## Notes`. Merge rules: union decisions; dedupe action items by (owner, normalized text); concatenate unique notes; keep attribution inline. This deterministic format is what makes the merge idempotent; it will be specified in full as part of the roll-up skill's plan.
- True same-file conflicts (two people hand-editing one canonical file) surface as normal Git conflicts and route to the file owner or admin.

### 4.5 Control plane and client update mechanism
- `manifest.json` is the source of truth; `.applied.json` records what the client has applied.
- skills bumped -> sync `CONTROL/skills/ -> .claude/skills/` (silent).
- structure bumped -> run pending `migrations/` in order, idempotently (gate if a migration is marked breaking).
- required_mcps changed -> announce to the user with the "how" string.
- min_client_version > installed -> warn / gate.
- policy_version bumped -> reload `policy.md`.

**Apply order and atomicity:** on each pull, first evaluate gates (`min_client_version`, any migration flagged breaking); if a gate is unmet, block the session before applying anything else. Otherwise apply in order: (1) structure migrations, (2) skills sync, (3) policy reload, then announce MCP changes last. `.applied.json` is updated per step, only after that step succeeds, so an interrupted pull resumes cleanly on the next session.

### 4.6 Privacy model
Three independent structural guards, with admin purge as backstop:
1. `private/` and `skills-local/` are gitignored.
2. The publish hook stages an explicit allowlist only.
3. (Future) sensitive data can be walled off in a separate repo.
Invariant: personal growth, self-reflection, 1:1 notes, and raw transcripts live only in `private/`, never centrally. Meeting rule: raw transcripts stay in `personal-meetings/`; only processed output is published.

### 4.7 TTL / freshness system (ported from the single-user OS)
Port `last_verified` frontmatter, per-type horizons, the SessionStart health hook, and `/memory-audit`. Applied to both private context and the shared hive, so group knowledge ages honestly. Horizons and health config live centrally (shippable via the control plane).

### 4.8 Skills model
- One universal skill set for everyone (shared skills from `CONTROL/skills` + personal `skills-local/`).
- Core skills: `/todo` (private target), `/memory-audit`, meeting processing (raw -> processed -> publish), plus the group operating skills.
- Role affinity (from `roles.json` + `personal-context`) only reorders/suggests; it never restricts.

### 4.9 Admin powers (GitHub org owner)
- Prune via ordinary commits (structure via CONTROL migrations).
- Purge leaked private data via a documented runbook: `git filter-repo` / BFG, force-push, rotate. Rare.
- Manage org teams, membership, branch protection, CODEOWNERS; sole owner of `CONTROL/`.

### 4.10 Repository topology (open-source monorepo + live instance)
```
team-brain-harness/                 # THE OPEN-SOURCE MONOREPO (the product)
├─ README.md                 # getting started: clone -> stand it up
├─ docs/                     # installation walkthrough + how-to guides
├─ installer/                # bootstrap: SSH keygen+guide, clone, wire hooks, private tree, role
├─ client-kit/               # what each member installs
│  ├─ CLAUDE.md              #   group operating model
│  ├─ hooks/                 #   the two sync hooks (session-start pull, publish push)
│  └─ skills/                #   shared skills (canonical source)
├─ hive-template/            # the empty shared-vault scaffolding
│  ├─ CONTROL/               #   manifest.json, skills/, migrations/, roles.json, policy.md
│  ├─ org/ product/ engineering/ design/ customers/ market/ knowledge/
│  ├─ projects/ decisions/ meetings/
│  └─ .gitignore             #   ignores private/ and skills-local/
└─ tools/                    # instantiate + vendor + upgrade scripts

  ── instantiate (installer/tools) ──▶

<org>-hive/                  # THE LIVE HIVE (private, per deployment; NOT open source)
├─ CONTROL/                  # vendored from monorepo at instantiation
├─ org/ product/ ...         # fills with real, live group content over time
└─ .gitignore
```
Runtime rule: clients only ever clone and sync the **live hive**. The monorepo is the source that generates the live hive and the installer, and the target for open-source contribution. Upgrading a deployment = re-vendor `CONTROL/` (and client-kit) from a newer monorepo release, which then propagates to clients via the control plane (4.5).

## 5. Onboarding

**Admin bootstrap (once):** create the GitHub org and repo, seed `CONTROL/` and the shared structure, define roles, set branch protection, invite members.

**Member onboarding (each person):**
1. Create a GitHub account (the admin helps non-technical members).
2. Run the installer: it installs the AI client, generates the SSH keypair and guides the user through pasting the public key into the GitHub UI (the admin assists non-technical members here), then clones the repo, wires the hooks, builds the `private/` tree, and records the person's role. The user's only manual responsibility is registering the printed public key.
3. A first-run interview seeds `personal-context` (role, focus, what they work on), analogous to the single-user `/onboarding` skill.

## 6. Rollout plan
1. Admin bootstraps the vault + control plane.
2. Pilot with engineering (most git-comfortable) to shake out the hooks and roll-up.
3. Add PM and UX.
4. Add support and sales, with the admin hand-holding GitHub setup.
5. Iterate skills and structure centrally via the control plane as needs emerge.

## 7. Open questions and risks
- **Merge intelligence for roll-up:** the merge must be reliable and idempotent; needs a well-tested skill and a deterministic canonical format.
- **Hook portability:** the AI client's hook model must support the SessionStart pull and publish push reliably, including offline and failure cases.
- **Non-technical UX:** even with an installer, SSH-key setup is the friction point; the teaching path must be smooth.
- **Purge cost:** history rewrite is disruptive; depends on private-by-default holding in practice.
- **Same-file conflict routing:** need a clear owner/resolution path for canonical shared files.
- **Scale of write contention:** rebase-retry is fine for a mid-size group; revisit if contention grows.

## 8. Relationship to existing artifacts
This builds on a single-user personal-knowledge OS pattern (folder taxonomy, templates, a memory/TTL subsystem, meeting processing, and simple per-person skills such as `/todo` and `/memory-audit`), which seeds `client-kit/` and `hive-template/` inside the open-source monorepo (`team-brain-harness`). The group layer adds: the monorepo packaging and instantiation tooling, the two sync hooks, the control plane, the roll-up mechanism, the privacy allowlist, and the admin runbook.
