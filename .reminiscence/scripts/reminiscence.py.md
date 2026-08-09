---
source: scripts/reminiscence.py
source_sha: 3b7a91105a29614ecc2e6bd00f0b45fdffd4ecfd
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
MIRROR, DIRTY, GRAPH_CACHE, INDEX, GEN_START, GEN_END, SOURCE_EXTS, DEFAULT_IGNORES, PROSE_SECTIONS, SLOP_OPENERS, repo_root, tracked_files, blob_sha, load_ignores, ignored, sources, note_path, dir_note_path, parse_note, render_note, split_generated, read_note, write_note, skeleton_body, build_graph, generated_block, cmd_path, cmd_sources, cmd_scaffold, cmd_map, skeleton_body_tail, write_index, collect_notes, audit, lint, cmd_verify, cmd_unfilled, topological, cmd_stamp, drop_dirty, cmd_dirty, cmd_status, cmd_prune, main

## External
__future__, argparse, datetime, fnmatch, hashlib, json, os, posixpath, subprocess, sys
<!-- reminiscence:generated:end -->

## Role
The only thing that writes the generated region of a note. Every skill verb is a thin wrapper over one of these subcommands.

## Interfaces
`map` always recomputes the whole graph and writes only notes whose content changed. Callers get minimal diffs without an incremental code path to get wrong.

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
