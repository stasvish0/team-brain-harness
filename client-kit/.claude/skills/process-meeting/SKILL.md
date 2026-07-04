---
name: process-meeting
description: Turn a raw meeting transcript in private/personal-meetings/ into a shareable, structured contribution and publish it to the shared meeting inbox.
---

# Process a meeting

Use this after a meeting whose raw transcript is saved under `private/personal-meetings/`. The raw transcript NEVER leaves this machine; you publish only a structured summary.

## Steps

1. **Read the raw transcript** the member points you at (under `private/personal-meetings/`). Summarize it into three lists:
   - `decisions`: short decision statements (strings).
   - `action_items`: objects `{owner, text}` (owner is the assignee's author-id or name).
   - `notes`: other noteworthy points (strings).

2. **Refresh the shared tree before choosing an id** (so you see meetings other members already created):
   `python3 .claude/hooks/sync_pull.py --repo <repo>` (or a plain `git pull`).

3. **Discover-or-create the meeting id.** With the meeting date `YYYY-MM-DD`, list existing dirs:

   ```python
   from lib.meeting_rollup import find_meeting_dirs, slugify
   find_meeting_dirs("<repo>", "2026-07-04")
   ```

   If one plausibly matches this meeting (reconcile title variants like "standup" vs "daily standup" yourself), reuse its id. Otherwise create `<date>-<slugify(title)>`.

4. **Determine your author-id** (one stable identity, used everywhere): a handle from your `private/personal-context` profile if you have one; otherwise the slugified local-part of `git config user.email` (e.g. `alice@x.com` -> `alice`).

5. **Write the contribution** to `meetings/<id>/_inbox/<author-id>.md` with exactly a sentinel comment then a fenced json block:

   <!-- team-brain-harness:rollup-data -->
   ```json
   {"meeting_id": "<id>", "title": "<title>", "date": "<date>",
    "author": "<author-id>", "decisions": [], "action_items": [], "notes": []}
   ```

6. **Publish** just the shared contribution (raw stays private):
   `python3 .claude/hooks/publish.py --repo <repo> --allowlist <repo>/publish_allowlist.txt --message "meeting <id>"`

The roll-up into one canonical note happens automatically on the next member's session start (the SessionStart hook merges every attendee's inbox contribution into one `meetings/<id>/<slug>.md`, deletes the inbox, and pushes). You do not merge by hand.
