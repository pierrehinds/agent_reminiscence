---
source: hooks/post_tool_use.py
source_sha: 0a957579d4ca2d302dcd373d60ea7fb74f6f6055
filled_by: main
updated: 2026-08-09
---

<!-- reminiscence:generated:start -->
## Uses
- scripts/reminiscence.py

## Used by
—

## Tested by
—

## Exports
main

## External
__future__, json, os, sys
<!-- reminiscence:generated:end -->

## Role
Records which sources were edited this turn. Pure append; the Stop hook does the work.

## Interfaces
—

## Why it's like this
Deliberately does not refresh notes. Code churns mid-task, so a per-edit
refresh burns tokens on prose that goes stale again three edits later.

Routes by `scope_for_path`, not cwd. One session sitting at a monorepo root can
edit files belonging to several different mirrors in a single turn.

## Gotchas
Silently ignores paths outside the repo and files whose extension is not in `SOURCE_EXTS`, so editing a README never enqueues work.

## Related
- [[hooks/stop.py]] — drains this queue
