---
name: hive-audit
description: Re-verify stale/expired notes (stamp the ones still true), and surface near-duplicates. On-demand freshness maintenance for the shared hive.
---

# Hive audit

On-demand freshness pass over tracked notes (those with `last_verified` front-matter).

## Steps

1. **Find stale/expired notes:**
   ```python
   from datetime import date
   from lib.freshness import read_health_config, scan
   cfg = read_health_config("<repo>")
   [r for r in scan("<repo>", cfg, date.today()) if r["status"] in ("stale", "expired")]
   ```

2. **Re-verify each against current knowledge / live data.** For each stale or expired note, read it and judge: is it still true?
   - **Still true** -> add it to a `to_stamp` list.
   - **No longer true** -> do NOT stamp. Surface it to the user with a proposed rewrite or deletion. Never auto-rewrite or auto-delete shared knowledge.

3. **Stamp + commit the confirmed notes** (one transaction; private stamps stay local):
   ```python
   from lib.freshness import commit_stamps
   commit_stamps("<repo>", to_stamp, date.today())
   ```
   If it raises (a concurrent push conflict), tell the user the stamp did not land and to re-run; the repo is left clean.

4. **Surface duplicates** (do not auto-merge; merging shared notes is destructive):
   ```python
   from lib.freshness import find_duplicates
   find_duplicates("<repo>", cfg)
   ```
   Report each cluster to the user and propose a merge for them to confirm.
