# Note format

Every note lives at `.reminiscence/<source path>.md` — the source path verbatim,
plus `.md`. **The source path is relative to that mirror's root**, i.e. the
folder containing `.reminiscence/`. For a single-package repo that is the repo
root, so paths read repo-relative; under a monorepo scope they are relative to
the scoped package, and edges leaving it read `../../other/package/file.py`.

The `.md` suffix is not cosmetic: it keeps the mirror out of
`**/*.py` globs, so linters, type checkers and test collectors never try to
parse a note as code. It also disambiguates `menu.py` from `menu.ts`.

## Full shape

```markdown
---
source: src/app/routes/menu.py
source_sha: 9a3f2c1e4b...
filled_by: main
updated: 2026-08-09
---

<!-- reminiscence:generated:start -->
## Uses
- src/app/services/menu_cache.py
- src/app/models/menu.py

## Used by
- src/app/routes/__init__.py

## Tested by
- tests/test_menu.py

## Exports
get_menu, MenuView, MENU_TTL

## External
fastapi, pydantic
<!-- reminiscence:generated:end -->

## Role
Public HTTP surface for menu reads. Everything below it is cache-aware; nothing
above it is.

## Interfaces
`get_menu` returns a view, not a model — callers that need to mutate must go
through the service layer or their writes are silently dropped.

## Why it's like this
Filtering happens in Python rather than SQL because the planner picked a bad
index under the composite WHERE (#412). Revisit past ~50k rows.

## Gotchas
The cache key omits `include_hidden`. Intentional — the hidden set is tiny and
re-filtering beats a second cache entry. Adding it to the key doubles cache
pressure for no gain.

## Related
- [[src/app/services/menu_cache.py]] — owns the TTL constant this file reads
- #412
```

## Frontmatter

| Field | Written by | Meaning |
| --- | --- | --- |
| `source` | `scaffold` | Scope-relative path this note documents. |
| `source_sha` | `stamp` | Git blob hash of the source at last prose fill. |
| `filled_by` | `stamp` | `main` or `haiku` — provenance of the prose. |
| `updated` | `stamp` | Date of last prose fill. |

`source` is scope-relative, so it is directly usable by an agent whose working
directory is the scope root.

**Fill state derives entirely from `source_sha`**, with no separate bookkeeping:

- absent → never filled
- present, ≠ current blob hash → prose is stale
- present, = current blob hash → clean

Nothing can desync, and `fill` gets resumability for free — a stamped note is a
completed note, so an interrupted bulk fill resumes exactly where it stopped.

`filled_by: haiku` marks prose as **provisional**. Diffusion fill overwrites it
with `main`. This makes bulk fill safe to run at any time: cold prose can only
ever be replaced by something better, never compete with it.

## The two regions

Everything between the `reminiscence:generated` markers is owned by `map` and
rewritten from the `ast` graph on every run. Hand edits there are destroyed
without warning — and correctly so, because a hand-written import graph is wrong
the moment the next import lands.

Everything after `:end -->` is prose, owned by whoever fills it. `map` never
reads or touches it. This is verified: re-running `map` over a note with
hand-written prose leaves the prose byte-identical.

## Generated sections

| Section | Source |
| --- | --- |
| `Uses` | Resolved outbound imports, as repo paths. |
| `Used by` | Inverted edge set, excluding test files. |
| `Tested by` | Inbound edges from `tests/`, `test_*.py`, `*_test.py`. |
| `Exports` | Top-level defs/classes/assignments, or `__all__` when present. |
| `External` | Unresolvable imports, by top-level package name. |

`Used by` is the section that earns the design. Outbound imports are readable
from the top of the file; "who calls this?" normally costs a repo-wide grep.
Precomputing the inversion turns it into a `Read`.

Edges are computed against the **whole repository**, never just the covered
scope. An entry may therefore point outside the mirror — a real file with no
note of its own. Read the source directly. Scoping the graph as well as the
coverage would turn such an edge into a bare `External` entry, losing the link
entirely.

## Directory notes

`_dir.md` sits in each mirrored directory and carries the folder-level story, so
per-file notes never repeat it. It has no generated region and no `source_sha` —
it is prose only, and `verify` does not track its freshness.

## Empty sections

`—` is the correct, complete value for a section with nothing real to say. It is
not a TODO. Do not fill it to look thorough.
