---
source: scripts/reminiscence.py
source_sha: af351b5245b8f3952123c8f628b482830636fa1b
filled_by: main
updated: 2026-08-09
---

<!-- reminiscence:generated:start -->
## Uses
- scripts/extractors/python.py

## Used by
- hooks/post_tool_use.py
- hooks/stop.py

## Tested by
—

## Exports
MIRROR, GRAPH_CACHE, INDEX_NAME, GEN_START, GEN_END, SOURCE_EXTS, DEFAULT_IGNORES, PROSE_SECTIONS, SLOP_OPENERS, repo_root, scope_prefix, scope_for_path, in_scope, to_scope, to_repo, tracked_files, blob_sha, load_ignores, ignored, sources, visible_python, note_path, mirror_root, parse_note, render_note, split_generated, read_note, write_note, skeleton_tail, skeleton_body, build_graph, generated_block, rewrite_notes, write_index, collect_notes, audit, lint, resolve, cmd_path, cmd_sources, cmd_scaffold, cmd_map, cmd_verify, cmd_unfilled, topological, cmd_stamp, drop_dirty, cmd_dirty, cmd_status, other_mirrors, cmd_scopes, cmd_prune, main

## External
__future__, argparse, datetime, fnmatch, hashlib, json, os, posixpath, subprocess, sys
<!-- reminiscence:generated:end -->

## Role
The only thing that writes the generated region of a note. Every skill verb is a thin wrapper over one of these subcommands.

## Interfaces
Two path spaces, and confusing them is the easiest way to break this file:
*repo-relative* is what git and the resolver speak, *scope-relative* is what
notes contain. `to_scope` / `to_repo` are the only sanctioned crossings.

`map` always recomputes the whole graph and writes only notes whose content
changed, so callers get minimal diffs without an incremental code path.

`scope_prefix(creating=...)` is the sharp edge. Falling back to the repo root
when no mirror is found is only safe while creating one; for any other verb it
invents a whole-repo scope, and `map` run from the root of a scoped monorepo
would then scaffold a second mirror over every package. Non-creating callers
adopt a lone existing mirror instead, and refuse when there are several.

## Why it's like this
Incremental mapping was rejected. Editing A's imports changes B's `Used by`,
so a correct incremental pass has to walk to affected neighbours anyway.
Full recompute plus write-if-changed is simpler and provably right; the
blob-hash parse cache keeps it cheap.

`blob_sha` reimplements git's hash in-process rather than shelling out to
`git hash-object`. `map` hashes every source on every run — one subprocess
per file made pre-commit unusable on a large repo.

## Gotchas
`write_note` compares content before writing. That is not an optimisation,
it is what makes `map` idempotent — without it every run touches every mtime
and the pre-commit gate churns.

`verify` intentionally does not fail on UNFILLED. Partial prose is the normal
steady state under diffusion; failing on it would force a bulk fill nobody
asked for.

## Related
- [[scripts/extractors/python.py]] — supplies the facts; this file owns rendering and bookkeeping
