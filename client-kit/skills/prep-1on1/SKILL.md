---
name: prep-1on1
description: Prepare talking points for a 1:1 with a report, peer, or manager, from shared hive context plus your private 1:1 history. Use when "prep for 1:1 with X", "what should I discuss with X", "1:1 prep X".
---

# Prep a 1:1

Build talking points for the member's upcoming 1:1 with **$ARGUMENTS**. The counterpart may be a report, a peer, or the member's own manager; the hive is cross-functional, so do not assume a reporting relationship. The prep sheet is PRIVATE: it is printed for the member and logged under `private/`, never published.

## Step 1: Gather context

1. **Shared hive context.** Search `org/` for a note on this person (role, team, focus). If they lead or belong to a team, read that team's note under `org/` and any active `projects/` they own or contribute to. These are shared facts; read but do not edit them here.
2. **Private 1:1 history.** Read `private/personal-context/one-on-ones/<name>.md` if it exists: the last entry (date, what was discussed, commitments), open follow-ups, career goals, and feedback history. This file is the member's private log and is the primary source for continuity.
3. **Private tasks.** Read `private/TODO.md` and pull any items owned by, waiting on, or tagged to this person.

## Step 2: Connection check

Note which MCPs are connected and responding (e.g. a chat tool like Slack, an issue tracker, a meetings/transcripts tool). Skip any that are absent and note the gap in the output rather than failing. The hive declares no required MCPs, so treat all live tools as optional enrichment on top of the vault.

## Step 3: Pull live signals (only for connected tools, in parallel)

- **Chat:** recent messages by or mentioning this person (last ~7 days): concerns, wins, decisions, anything worth a conversation.
- **Issue tracker:** their in-flight and recently completed work; flag blocked or stale items and context-switching patterns.
- **Meetings/transcripts:** recent meetings involving them; flag any not yet run through /process-meeting.

## Step 4: Assemble the talking points

Combine the vault context (Step 1) with any live signals (Step 3). Be specific: real names, dates, item references. No generic filler. Structure:

- **Follow-ups from last time** - open commitments from the private 1:1 log and TODO.
- **Their current work** - projects, risks, blockers from `org/` and `projects/`, cross-referenced with tracker signals.
- **Growth / career** - progress on goals from the private log.
- **To discuss** - concrete items surfaced from chat, tracker, and meetings.
- **Questions to ask** - thoughtful, grounded in the context above.

## Step 5: Display and log

1. Print the prep sheet to the conversation (this output is ephemeral).
2. Append a dated stub to `private/personal-context/one-on-ones/<name>.md` (create the file and folder if absent) with the date and the items you planned to raise, so the next prep has continuity. After the 1:1, the member can fill in what was actually discussed and any new commitments.

Nothing in this skill publishes. If a decision comes out of the 1:1 that the team should see, use /decision.
