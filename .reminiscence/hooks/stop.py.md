---
source: hooks/stop.py
source_sha: d539865471622bae17d5d0b6c48fae81218ccaab
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
STATE, emit, main

## External
__future__, json, os, sys
<!-- reminiscence:generated:end -->

## Role
The diffusion mechanism. Coverage grows because this fires at the end of every turn that touched code, not because anyone remembers a command.

## Interfaces
Returns `{"decision": "block", "reason": ...}` on stdout. Exits 0 silently on every failure path.

## Why it's like this
Two stages because the halves have different costs. Re-mapping is free and
happens unconditionally; only missing prose is worth interrupting a turn for.

Loop safety does not use `stop_hook_active` — that field is not in the
documented Stop payload. Instead the block condition *is* the dirty set, and
the agent's response clears it, so the next Stop has nothing to say.
`.stop_state` is only the backstop for a turn that does not comply.

## Gotchas
The bare `except` at module level is deliberate. A memory layer that can
break someone's session is worse than one that occasionally misses a file.

It re-maps every source, not just the dirty ones, because a dirty file's
edits change its neighbours' back-edges.

The `stamp` command in the block reason is built with an absolute script path
derived from `__file__`. The agent receiving it has cwd set to the target repo,
not the skill directory, so a relative path silently fails to resolve.

## Related
- [[hooks/post_tool_use.py]] — fills the queue this drains
