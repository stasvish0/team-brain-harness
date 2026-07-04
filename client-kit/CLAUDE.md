# Group Hive-Brain Client

This is a client of the group hive-brain. Shared context is synced with the group
via two hooks: `sync_pull.py` pulls the latest shared context at session start, and
`publish.py` pushes your allowlisted changes upstream.

Anything under `private/` is local-only. It never leaves this machine and is never
published to the group.
