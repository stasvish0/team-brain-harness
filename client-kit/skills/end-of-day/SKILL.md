---
name: end-of-day
description: End-of-day wrap-up: process today's meetings, triage the TODO list, and surface decisions worth recording. Use when "end of day", "wrap up", "done with meetings", "eod".
---

# End of day

Close out the day in sequence. Complete each step fully before the next.

## Step 1: Process today's meetings

For each raw transcript from today sitting in `private/personal-meetings/`, run the `/process-meeting` flow (turn it into a shared, structured contribution and publish it to the meeting inbox; the raw transcript stays private). If there are several, do them one at a time.

While processing, retain across all of today's meetings:
- **Decision candidates** - moments where the team settled something that deserves a durable, shared ADR.
- **Follow-ups by owner** - action items grouped by the person who owns them.

## Step 2: Triage the TODO list

Run the `/todo` triage pass: wake due snoozed items, park future-dated ones, sweep completed items to Done, and show the triage report over `private/TODO.md`.

## Step 3: Surface decisions and follow-ups

Re-display, from Step 1:

**Decision candidates.** For each: the meeting it came from, the decision in one line, and why it may warrant a formal record. Then ask: "Want me to record any of these with /decision?" (which writes a shared ADR and publishes it).

**Follow-ups by owner.** The grouped action items. Then ask: "Want me to draft messages to anyone about these?" Draft any the member wants into `private/personal-drafts/` for review before sending; do not send anything automatically.

Nothing in Step 2 or 3 publishes on its own. Only /process-meeting (Step 1) and an explicit /decision push to the hive.
