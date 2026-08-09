#!/usr/bin/env python3
"""PostToolUse: record which sources were edited this turn.

No model involvement and no note rewriting — just an append. Refreshing a note
per edit would burn tokens on prose that goes stale again three edits later, so
this only accumulates the work queue that the Stop hook drains.

The queue is written into whichever mirror owns the file, not the session's cwd:
one turn at a monorepo root can touch several scopes.

Every failure path exits 0. A memory layer that can break someone's session is
worse than one that occasionally misses a file.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not file_path:
        return 0

    import reminiscence as rem

    root = rem.repo_root()
    try:
        rel = os.path.relpath(os.path.abspath(file_path), root).replace(os.sep, "/")
    except ValueError:
        return 0
    if rel.startswith("../"):
        return 0
    if os.path.splitext(rel)[1] not in rem.SOURCE_EXTS:
        return 0

    prefix = rem.scope_for_path(root, rel)
    if prefix is None:
        return 0
    if rem.ignored(rem.to_scope(rel, prefix), rem.load_ignores(root, prefix)):
        return 0

    dirty = os.path.join(root, rem.mirror_root(prefix), ".dirty")
    existing = set()
    if os.path.exists(dirty):
        with open(dirty, encoding="utf-8") as handle:
            existing = {line.strip() for line in handle if line.strip()}
    existing.add(rel)
    os.makedirs(os.path.dirname(dirty), exist_ok=True)
    with open(dirty, "w", encoding="utf-8") as handle:
        handle.write("\n".join(sorted(existing)) + "\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(0)
