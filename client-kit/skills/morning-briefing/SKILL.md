---
name: morning-briefing
description: Start-of-day briefing: what changed in the shared hive overnight, your calendar, action items, and blockers. Use when "good morning", "start my day", "what happened overnight", "morning briefing".
---

# Morning briefing

Catch the member up at the start of their day. The briefing is PRIVATE (saved under `private/`); it reads the shared hive plus any connected tools but publishes nothing.

The harness-native "overnight" is **what landed in the shared brain since the member last synced**: other members publish decisions, meeting roll-ups, and project updates while the member is offline, and the session-start pull brings them in. Surface those first.

## Step 0: Setup

1. Determine today's date.
2. **Sync and diff the hive.** Pull, then find what changed since the last local sync:
   `python3 .claude/hooks/sync_pull.py --repo <repo>`
   Then review recent shared-vault history to see what teammates contributed overnight:
   `git -C <repo> log --since=yesterday --name-status -- org product engineering design customers market knowledge projects decisions meetings`
   Read the notable new/changed shared notes (new `decisions/`, merged `meetings/<id>/`, updated `projects/`).
3. Read `private/TODO.md`.

## Step 1: Connection check

Note which MCPs are connected (e.g. calendar, chat, issue tracker, GitHub via `gh`). Skip absent ones gracefully. All are optional enrichment; the hive diff and TODO are the guaranteed backbone.

## Step 2: Gather (in parallel where possible)

- **Hive overnight** (always): decisions recorded, meetings rolled up, projects updated since last sync, and who contributed. From Step 0.
- **Calendar** (if connected): today's events with times (in the member's timezone) and attendees. Flag any 1:1s by cross-referencing attendees against `org/` notes.
- **Action items** (always): overdue and due-today items from `private/TODO.md`; scan `projects/` for milestones due today or this week.
- **Blockers** (if chat/tracker connected): open blockers and any escalation/urgent chatter in the last 24h. Also fold in blockers noted in overnight meeting roll-ups.
- **Code** (if `gh` available): PRs awaiting the member's review and stale open PRs (> 3 days).

## Step 3: 1:1 prep

If the calendar has a 1:1 today, generate a short talking-point block for each by reading `private/personal-context/one-on-ones/<name>.md` and the person's `org/` context. For a full sheet, point the member at /prep-1on1.

## Step 4: Compile and save

Assemble, leading with what needs action:

```
# Morning Briefing - <YYYY-MM-DD>

## Attention required
[Blockers, escalations, overdue items - highest priority first]

## Overnight in the hive
[New decisions, rolled-up meetings, project updates since last sync, with who contributed]

## Today's schedule
[Events with time and attendees; 1:1s flagged]

## Action items
[Overdue / Due today / Due this week]

## Code
[PRs needing review, stale PRs - only if gh available]

## 1:1 prep
[Only if there is a 1:1 today]
```

Save to `private/personal-reviews/<YYYY-MM-DD>.md`, display it, and end with: "What do you want to dig into first?"
