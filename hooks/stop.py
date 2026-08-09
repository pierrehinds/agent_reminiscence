#!/usr/bin/env python3
"""Stop: heal the graph silently, then ask for prose only when it's needed.

This is the diffusion mechanism. Coverage grows because this hook fires at the
end of every turn that touched code, not because anyone remembers to run a
command.

Two-stage by design:
  1. `map` reruns over every mirror that saw an edit. Edges are derived facts,
     so this needs no model and produces no output.
  2. Only if prose is genuinely missing or stale does it block, and only with
     the specific file list.

Loop safety without `stop_hook_active`: the block condition is the dirty set
itself, and the agent's response (write prose, then `stamp`) clears it — so the
next Stop finds nothing to say. `.stop_state` is the backstop for the case
where the agent does not comply, so a non-cooperating turn stalls once rather
than forever.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))


def emit(payload: dict) -> int:
    print(json.dumps(payload))
    return 0


def main() -> int:
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        pass

    import reminiscence as rem

    root = rem.repo_root()
    scopes = rem.other_mirrors(root)
    if not scopes:
        return 0

    graph = None
    pending: list[tuple[str, str]] = []   # (scope prefix, repo-relative source)

    for prefix in scopes:
        dirty_path = os.path.join(root, rem.mirror_root(prefix), ".dirty")
        if not os.path.exists(dirty_path):
            continue
        with open(dirty_path, encoding="utf-8") as handle:
            dirty = sorted({line.strip() for line in handle if line.strip()})
        if not dirty:
            continue

        # Stage 1: the graph repairs itself, silently and for free. Built once
        # and shared — visibility is repo-wide regardless of how many mirrors
        # need rewriting.
        if graph is None:
            graph = rem.build_graph(root, force=set(dirty))
        srcs = rem.sources(root, prefix)
        rem.rewrite_notes(root, prefix, srcs, graph)
        rem.write_index(root, prefix, graph, srcs)

        audit = rem.audit(root, prefix)
        needs = set(audit["UNFILLED"] + audit["PROSE-STALE"])
        stale = [p for p in dirty if p in needs]
        if stale:
            pending.extend((prefix, p) for p in stale)
        else:
            rem.drop_dirty(root, prefix, dirty)

    if not pending:
        _clear_state(root)
        return 0

    signature = "\n".join(f"{s}:{p}" for s, p in pending)
    if _seen_before(root, signature):
        _clear_state(root)
        return emit({
            "systemMessage": (
                f"reminiscence: {len(pending)} note(s) still unfilled; "
                "graph is up to date. Not asking again this turn."
            )
        })
    _remember(root, signature)

    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "reminiscence.py",
    )

    lines, commands = [], []
    by_scope: dict[str, list[str]] = {}
    for prefix, source in pending:
        by_scope.setdefault(prefix, []).append(source)
    for prefix, srcs in by_scope.items():
        label = prefix or "(repo root)"
        for source in srcs:
            lines.append(f"  - {source}  ->  {rem.note_path(source, prefix)}")
        scoped = " ".join(rem.to_scope(s, prefix) for s in srcs)
        commands.append(
            f"  python3 {script} stamp {scoped} --by main --scope {prefix or '.'}"
            f"   # scope: {label}"
        )

    reason = (
        "reminiscence: the graph has been re-mapped automatically, but these "
        "files were edited this turn and their notes still need prose:\n\n"
        + "\n".join(lines)
        + "\n\nFor each one, write ONLY what the code cannot say for itself: why "
        "it is built this way, what you rejected, constraints, gotchas you hit "
        "this turn. Do not restate signatures or narrate control flow — if a "
        "section has nothing real, leave it as an em-dash. Never edit between "
        "the reminiscence:generated markers.\n\nThen run:\n"
        + "\n".join(commands)
    )
    return emit({"decision": "block", "reason": reason})


def _state_path(root: str) -> str:
    return os.path.join(root, ".git", "reminiscence.stop_state")


def _seen_before(root: str, signature: str) -> bool:
    path = _state_path(root)
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read() == signature
    except OSError:
        return False


def _remember(root: str, signature: str) -> None:
    path = _state_path(root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(signature)


def _clear_state(root: str) -> None:
    path = _state_path(root)
    if os.path.exists(path):
        os.remove(path)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(0)
