---
name: help
description: List the hive skills and how they work. Use when "help", "what can you do", "list commands", "what skills are there".
---

# Help

Display a guide to the skills available in this hive client. Group them by whether they touch the shared brain or stay private, then show conversational triggers. Format as clean tables.

## How the hive works (state this briefly first)

- **Shared vault** (`org/`, `product/`, `engineering/`, `design/`, `customers/`, `market/`, `knowledge/`, `projects/`, `decisions/`, `meetings/`): synced with the whole team. Pulled at session start; published only via the allowlisted publish hook.
- **Private tree** (`private/`): local-only, never syncs. Holds `TODO.md`, raw meeting transcripts, personal notes, drafts, and personal reviews.
- Every session **pulls** the latest shared context on start. Publishing is always an explicit, allowlisted act.

## Skills

### Shared (contribute to the team brain)

| Skill | What it does |
|-------|--------------|
| `/onboarding` | **Run first.** Interview to complete your private profile after install. |
| `/process-meeting` | Turn a raw transcript in `private/personal-meetings/` into a shared, structured contribution and publish it to the meeting inbox (raw stays private). |
| `/decision <slug>` | Record an ADR-style decision and publish it to the shared `decisions/` tree. |
| `/hive-audit` | Re-verify stale/expired shared notes, stamp the ones still true, and surface near-duplicates. |

### Private (personal, never published)

| Skill | What it does |
|-------|--------------|
| `/morning-briefing` | Start-of-day: what changed in the hive overnight, calendar, action items, blockers. |
| `/todo` | Show and triage `private/TODO.md`. `/todo add <text>`, `/todo done <text>`, `/todo snooze <text> <date>`. |
| `/prep-1on1 <name>` | Talking points for a 1:1, from shared `org/` context plus your private 1:1 log. |
| `/prep-tomorrow-meetings` | Pull tomorrow's calendar, run `/prep-1on1` for any 1:1s, write per-meeting briefings and prep tasks. |
| `/weekly-review` | Your private weekly cross-team rollup from the hive plus your own notes. |
| `/end-of-day` | Wrap up: process today's meetings, then triage the TODO, then surface decisions worth recording. |
| `/help` | This guide. |

## Usage tips

- **Fresh install:** `/onboarding`
- **Start your day:** `/morning-briefing`
- **After a meeting:** `/process-meeting`
- **Before a 1:1:** `/prep-1on1 <name>`
- **When you settle something:** `/decision <slug>`
- **End of day:** `/end-of-day`
- **End of week:** `/weekly-review`
- **Keep shared knowledge fresh:** `/hive-audit`

## Conversational triggers

You do not have to type a slash command; just talk.

| If you say... | Runs |
|---------------|------|
| "set up", "first run", "onboard me" | `/onboarding` |
| "good morning", "start my day", "what happened overnight" | `/morning-briefing` |
| "process this meeting", "log the meeting" | `/process-meeting` |
| "prep for 1:1 with X", "what should I discuss with X" | `/prep-1on1 X` |
| "we decided to X", "record this decision" | `/decision` |
| "my todos", "what's on my list" | `/todo` |
| "prep for tomorrow", "tomorrow's meetings" | `/prep-tomorrow-meetings` |
| "weekly review", "how did the week go" | `/weekly-review` |
| "end of day", "wrap up", "eod" | `/end-of-day` |
| "are my notes still true", "check freshness" | `/hive-audit` |
