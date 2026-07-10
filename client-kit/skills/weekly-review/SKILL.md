---
name: weekly-review
description: Generate your private weekly cross-team rollup from the shared hive plus your own notes. Use when "weekly review", "weekly rollup", "how did the week go", "cross-team status", "week in review".
---

# Weekly review

Compile the member's weekly rollup of what moved across the team. This is PRIVATE: it is the member's own read of the week, saved under `private/` and never published. (It reads the shared hive but does not author a shared roll-up; the meeting inbox already produces the shared canonical record.)

## Step 1: Refresh and scope

1. Pull the latest shared state: `python3 .claude/hooks/sync_pull.py --repo <repo>`.
2. Determine the current ISO week (`YYYY-WXX`) and the week's date range.
3. Note which MCPs are connected (chat, tracker) for optional enrichment; the hive is the guaranteed source.

## Step 2: Gather (parallelize where it helps)

From the **shared vault**, scoped to this week:
- `decisions/<YYYY>/` - decisions recorded this week (dates in front-matter or filename).
- `meetings/` - roll-up notes updated this week; pull open action items and decisions.
- `projects/` - status changes, new risks, milestones hit or slipped.
- `org/` - any team or org notes that changed.

From the **private tree**:
- `private/TODO.md` - completed items this week (celebrate), stale "This Week" items (> 7 days), and stalled "Waiting On" items.
- `private/personal-reviews/` - this week's daily briefings, for continuity.

From **connected tools** (optional): per-team chat highlights and tracker activity for the week, cross-referenced against `projects/`.

For a large hive, dispatch one subagent per active project or team plus a shared-context subagent, in parallel, then combine.

## Step 3: Compile

```
# Weekly Review - <YYYY-WXX>

## Cross-team status
[3-5 bullets per active team/project, from the vault + any tool signals]

## Decisions this week
[From decisions/ recorded this week]

## Dependencies and cross-team threads
[Where one team's work gates another's]

## Risks and watch items
[Slipping milestones, stalled work, escalations]

## Carried forward
[Stale TODO items + still-open meeting action items]

## Wins
[Shipped work, resolved blockers, notable progress]

## Next week focus
[Synthesized from risks, blockers, and project status]
```

## Step 4: Save and follow up

Save to `private/personal-reviews/<YYYY-WXX>.md` and display it.

Then ask: "Anything here worth sharing with the team? I can record decisions with /decision, or you can update the relevant `projects/` notes." If the member says yes to a project update, edit the shared `projects/` note and publish it with the publish hook; otherwise the review stays private.
