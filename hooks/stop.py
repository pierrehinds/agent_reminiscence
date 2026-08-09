#!/usr/bin/env python3
"""Stop: heal the graph silently, then ask for prose only when it's needed.

This is the diffusion mechanism. Coverage grows because this hook fires at the
end of every turn that touched code, not because anyone remembers to run a
command.

Two-stage by design:
  1. `map` reruns over the edited files. Edges are derived facts, so this needs
     no model and produces no output.
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

STATE = ".reminiscence/.stop_state"


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
    if not os.path.isdir(os.path.join(root, rem.MIRROR)):
        return 0

    dirty_path = os.path.join(root, rem.DIRTY)
    if not os.path.exists(dirty_path):
        _clear_state(root)
        return 0
    with open(dirty_path, encoding="utf-8") as handle:
        dirty = sorted({line.strip() for line in handle if line.strip()})
    if not dirty:
        _clear_state(root)
        return 0

    # Stage 1: the graph repairs itself, silently and for free.
    srcs = rem.sources(root)
    graph = rem.build_graph(root, srcs, force=set(dirty))
    for source in srcs:
        path = rem.note_path(source)
        parsed = rem.read_note(root, path)
        if parsed is None:
            meta, body = {"source": source}, rem.skeleton_body()
        else:
            meta, body = parsed
            meta.setdefault("source", source)
        before, _, after = rem.split_generated(body)
        if not after and rem.GEN_START not in body:
            before, after = "\n", rem.skeleton_body_tail()
        rem.write_note(
            root, path,
            meta,
            f"{before}{rem.GEN_START}{rem.generated_block(source, graph)}{rem.GEN_END}{after}",
        )
    rem.write_index(root, graph, srcs)

    # Stage 2: only prose needs a model.
    audit = rem.audit(root)
    needs_prose = [p for p in dirty if p in set(audit["UNFILLED"] + audit["PROSE-STALE"])]
    if not needs_prose:
        rem.drop_dirty(root, dirty)
        _clear_state(root)
        return 0

    signature = "\n".join(needs_prose)
    if _seen_before(root, signature):
        _clear_state(root)
        return emit({
            "systemMessage": (
                f"reminiscence: {len(needs_prose)} note(s) still unfilled; "
                "graph is up to date. Not asking again this turn."
            )
        })
    _remember(root, signature)

    listed = "\n".join(f"  - {p}  ->  {rem.note_path(p)}" for p in needs_prose)
    # Absolute, because the agent's cwd is the target repo, not the skill dir.
    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "scripts", "reminiscence.py",
    )
    paths = " ".join(needs_prose)
    reason = (
        "reminiscence: the graph has been re-mapped automatically, but these "
        "files were edited this turn and their notes still need prose:\n\n"
        f"{listed}\n\n"
        "For each one, write ONLY what the code cannot say for itself: why it "
        "is built this way, what you rejected, constraints, gotchas you hit "
        "this turn. Do not restate signatures or narrate control flow — if a "
        "section has nothing real, leave it as an em-dash. Never edit between "
        "the reminiscence:generated markers.\n\n"
        f"Then run:  python3 {script} stamp {paths} --by main"
    )
    return emit({"decision": "block", "reason": reason})


def _state_path(root: str) -> str:
    return os.path.join(root, STATE)


def _seen_before(root: str, signature: str) -> bool:
    path = _state_path(root)
    if not os.path.exists(path):
        return False
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
