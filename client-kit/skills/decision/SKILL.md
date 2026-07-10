---
name: decision
description: Record an ADR-style decision into the shared hive and publish it. Use when "record a decision", "document decision about X", "create ADR", "we decided to X", "log this decision".
---

# Record a decision

Capture a significant technical or organizational decision as a durable, shared ADR. Decisions are shared knowledge: they publish to the hive so the whole team (and every member's assistant) can see what was decided and why. The `decisions/` tree carries a 365-day freshness horizon, so a decision stays trusted for a year before /hive-audit asks you to re-confirm it.

The slug is: **$ARGUMENTS** (a short kebab-case name, e.g. `migrate-service-to-grpc`). If none was given, ask for one.

## Steps

1. **Refresh the shared tree first** so you write against the current state and avoid a same-day slug collision:
   `python3 .claude/hooks/sync_pull.py --repo <repo>` (or a plain `git pull`).

2. **Read the template** at `templates/decision.md`.

3. **Interview** the member to fill each section. Ask one question at a time:
   - What situation prompted this? (context, constraints, forces)
   - What exactly are you deciding? (the problem)
   - What did you decide?
   - What alternatives did you weigh, and why not those?
   - What is the rationale for this choice?
   - What are the consequences: what changes, what risks remain, what follow-ups?
   - Who was involved / needs to know? (deciders)
   - Any related decisions, specs, threads, or tickets to link?

4. **Fill the front-matter.** Set `date` and `last_verified` to today. Set `status` to `Accepted` unless the member says it is still `Proposed`. If this replaces an earlier decision, set `supersedes` to that file's path and update the older record's `status` to `Superseded`. Set `deciders` from the interview. Keep `type: decision`.

5. **Save** to `decisions/<YYYY>/<YYYY-MM-DD>-<slug>.md`, deriving `<YYYY>` from today and creating the year directory if it is absent.

6. **Publish or keep private.** Ask: "Publish this to the shared hive now, or keep it as a private draft?"
   - **Publish** (default for a settled decision):
     `python3 .claude/hooks/publish.py --repo <repo> --allowlist <repo>/publish_allowlist.txt --message "decision: <slug>"`
   - **Private draft** (still `Proposed`, or sensitive and not ready): save instead under `private/personal-decisions/<YYYY-MM-DD>-<slug>.md`. It stays local and never syncs. Tell the member to re-run /decision (or move the file into `decisions/<YYYY>/` and publish) when it is ready to share.

7. **Confirm** the path written and show a one-paragraph summary of the decision.
