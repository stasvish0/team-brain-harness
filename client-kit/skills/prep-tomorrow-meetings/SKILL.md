---
name: prep-tomorrow-meetings
description: Prepare for tomorrow's meetings: pull the calendar, run /prep-1on1 for any 1:1s, and write per-meeting briefings with prep tasks. Use when "prep for tomorrow", "what do I have tomorrow", "tomorrow's meetings".
---

# Prep tomorrow's meetings

Get the member ready for everything on tomorrow's calendar. Output is PRIVATE. Requires a connected calendar MCP; if none is connected, say so and offer to prep from a list the member pastes in.

## Step 1: Pull tomorrow's calendar

Fetch all of tomorrow's events. For each: title, start/end (in the member's timezone), attendees, and any agenda/description. Skip all-day blocks, OOO markers, and sub-15-minute events with no agenda.

## Step 2: Classify each meeting

- **1:1** - the member plus one other person.
- **Recurring team meeting** - a known recurring sync/standup/project meeting.
- **New / ad hoc / external** - anything else.

Identify 1:1 counterparts by cross-referencing attendees against `org/` notes and the member's `private/personal-context/one-on-ones/` logs.

## Step 3: Handle 1:1s

For each 1:1, invoke `/prep-1on1 <name>` and include its prep sheet inline under that meeting's section. Do not redo that work here.

## Step 4: Handle recurring team meetings (in parallel, connected tools only)

For each, gather:
- **Last occurrence** (meetings/transcripts tool, or the rolled-up note under `meetings/`): open action items, decisions, deferred topics, anything unresolved to raise.
- **Chat** (if connected): blockers, escalations, pending decisions in the relevant channel over the last ~3 days.
- **Tracker** (if connected and engineering-related): open/in-progress tickets for the team or project, flagging blocked or due-soon items.
- **Shared vault:** the relevant `projects/` and `org/` notes for current status.

## Step 5: Handle new / ad hoc / external meetings

- Search chat (if connected) for recent discussion of the topic or attendees (last ~7 days).
- Note external attendees' company/context if known.
- Check `private/TODO.md` for open items tied to this meeting or its people.
- Identify what the member needs to know walking in and any decision they will need to make.

## Step 6: Write the briefing

One section per meeting, chronological by start time:

```
### HH:MM - <title>
**Attendees:** ...
**Type:** 1:1 / recurring / ad hoc

**Context** - what happened last time, what's in flight, relevant signals.
**Bring to the meeting** - specific topics, decisions, updates to raise.
**Prep before it** - what the member must do or decide beforehand.
```

Save the full briefing to `private/personal-reviews/<tomorrow-YYYY-MM-DD>-meetings.md` and display it.

## Step 7: Add prep tasks

For each meeting needing concrete prep, add an item to `## This Week` in `private/TODO.md`:
`- [ ] Prep for <meeting> - <specific prep> _source: prep-tomorrow-meetings_ (+ <today>) (due <today>)`

Only add items with specific, real prep. Do not add generic "review the agenda" tasks.
