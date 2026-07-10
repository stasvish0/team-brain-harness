---
name: todo
description: Show and triage your private TODO list. Use when "show my todos", "what's on my list", "add X to my todos", "mark X done", "triage todos", "what do I need to do".
---

# TODO

Manage the member's personal task list. This is PRIVATE: it lives at `private/TODO.md` (seeded by the installer) and never syncs to the hive. Nothing here is published.

**$ARGUMENTS** can be:
- empty or `triage` -> show current state and run a triage pass
- `add <text>` -> append a new item to "This Week"
- `done <partial text>` -> mark a matching item complete and move it to Done
- `snooze <partial text> <YYYY-MM-DD>` -> park an item until a future date

## Date tags (append at end of line, after all text)

| Tag | Meaning |
|-----|---------|
| `(+ YYYY-MM-DD)` | Created date (every item) |
| `(due YYYY-MM-DD)` | Hard deadline (only when explicit) |
| `(start YYYY-MM-DD)` | Snooze / start date (parked items) |
| `(done YYYY-MM-DD)` | Completion date |

## If $ARGUMENTS starts with `add`

1. Parse the item text.
2. Append to the `## This Week` section: `- [ ] <text> _source: manual_ (+ <today>)`. Add `(due <date>)` only if a due date is explicit.
3. Confirm: "Added to This Week."

## If $ARGUMENTS starts with `snooze`

1. Parse the item text and start date.
2. Fuzzy-match one unchecked item (any section). If multiple match, list them and ask which.
3. Move it to `## Snoozed` and set `(start <date>)`.
4. Confirm: "Snoozed until <date>: <item>".

## If $ARGUMENTS starts with `done`

1. Fuzzy-match one unchecked item. If multiple match, list them and ask which.
2. Mark `[x]`, append `(done <today>)`, move it to the `## Done` section.
3. Confirm: "Marked done: <item>".

## If $ARGUMENTS is empty or `triage`

1. **Read `private/TODO.md`** in full.
2. **Wake snoozed items:** in `## Snoozed`, any item whose `(start <date>)` is today or past -> move to `## This Week`, drop the start tag, append `_(was snoozed)_`.
3. **Park future items:** in `## This Week` / `## Waiting On`, any unchecked item with `(start <date>)` in the future -> move to `## Snoozed`.
4. **Sweep completed:** move all `[x]` items from This Week / Waiting On to `## Done`.
5. **Classify** each remaining unchecked item: **Overdue** (past `(due)`), **Stale waiting** (in Waiting On, created > 7 days ago, no update), **Orphaned** (in Backlog, no `(+)` and no `_source:_`).
6. **Display the triage report** with sections: Active (This Week, with age in days), Overdue (needs decision), Waiting On (flag stale), Snoozed (with wake date), Backlog, Done (this week).
7. **Ask** what to do with overdue/stale items ("move to Backlog, or review one by one?") and apply the member's answer.
8. **Archive** Done items older than 7 days into `private/personal-reviews/<current-ISO-week>.md` under a "Completed" heading, then remove them from `TODO.md`.

## Rules

- Never delete or reorder items without confirmation.
- Delegated items always carry `_(owner: Name)_`.
- All date tags go at the very end of the line.
- This file is private. Do not publish it and do not copy its contents into any shared note.
