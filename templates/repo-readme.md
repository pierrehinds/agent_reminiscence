# .reminiscence

A memory graph for agents working on this repo. Every source file has a note at
the mirrored path:

```
src/app/routes/menu.py   ->   .reminiscence/src/app/routes/menu.py.md
```

The path is computed, never searched. Before editing a file, read its note.

## What a note is for

Primarily **navigation**. The generated region carries pre-resolved links to the
files this one uses and the files that use it, so you traverse the codebase by
following edges instead of grepping. `INDEX.md` maps every symbol to its
defining file.

Secondarily **context**: why the code is like this, what was tried and failed,
gotchas. Never a restatement of the code — anything you could learn by reading
the file does not belong in its note.

## Two regions, two owners

Everything between the `reminiscence:generated` markers is written by
`reminiscence map` from the import graph. **Do not hand-edit it** — it is
rewritten on every map, and a hand-written import graph is wrong as soon as the
next import lands.

Everything below the end marker is prose. `map` never touches it.

## Sparse prose is normal

Most notes will have edges but little or no prose. That is the intended steady
state: prose accumulates on the files people actually work on. An empty section
is written `—`, and that is a complete answer, not a TODO.

## Commands

```bash
reminiscence status     # coverage
reminiscence map        # rebuild the graph (free, idempotent, safe anytime)
reminiscence verify     # what is missing, orphaned, or stale
```
