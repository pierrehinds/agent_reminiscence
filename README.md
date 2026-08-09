# Reminiscence

A traversable memory graph for codebases, as a Claude skill.

Every source file gets a markdown note at the mirrored path:

```
src/app/routes/menu.py   ->   .reminiscence/src/app/routes/menu.py.md
```

The note path is **computed, never searched** — `.reminiscence/` + source path +
`.md`. One `Read` with a derived path. No `Glob`, no `Grep`.

## Why

An agent asked to change one file needs to know what that file touches and what
touches it. Today it finds out by grepping: expensive, lossy, and unable to
resolve `from ..services import menu_cache` to a real path without guessing.

A reminiscence note answers that from a precomputed graph:

```markdown
<!-- reminiscence:generated:start -->
## Uses
- src/app/services/menu_cache.py
- src/app/models/menu.py

## Used by
- src/app/routes/__init__.py

## Tested by
- tests/test_menu.py
<!-- reminiscence:generated:end -->

## Why it's like this
Filtering happens in Python rather than SQL because the planner picked a bad
index under the composite WHERE (#412). Revisit past ~50k rows.
```

`Used by` is the section that earns it. Outbound imports are readable from the
top of the file; *"who calls this?"* normally costs a repo-wide grep.

The second job is keeping source files readable for humans. Agents over-comment
— banner blocks, restated lines, redundant docstrings. That commentary exists
because the agent needed the context, but the code is the wrong home for most of
it. The note gives it a right one.

## The design in one table

| | Built by | Cost | Coverage |
| --- | --- | --- | --- |
| **Edges** — `Uses`, `Used by`, `Exports` | `ast`, deterministic | free | **exhaustive from day one** |
| **Prose** — role, why, gotchas | a model | tokens | **diffuses as work touches files** |

`init` and `map` are both free, so the web is fully traversable immediately with
zero prose written. Diffusion affects prose *density*, never connectivity — which
is what makes it safe. If edges diffused too, every unfilled file would be a dead
end and traversal would collapse back into grep.

Diffusion also produces *better* notes than a bulk pass. Why-it's-like-this and
what-was-rejected are not recoverable by reading a file cold. An agent that just
spent a turn editing `menu.py` knows things no cold pass can reconstruct.

## Usage

```bash
/reminiscence init          # mirror of empty skeleton notes          free
/reminiscence map           # populate the graph                      free
/reminiscence status        # coverage report                         free
/reminiscence fill [glob]   # bulk cold-fill prose, Haiku subagents    $
/reminiscence map-and-fill  # both                                     $
/reminiscence               # detect state, run the per-turn workflow
```

## Monorepos

The mirror is created wherever you run `init`, and every later command finds it
by walking up from your working directory — the way git finds `.git`. So scope
is just where your terminal is:

```bash
cd services/api && /reminiscence init    # covers services/api only
/reminiscence init --scope libs/shared   # or name the folder explicitly
```

Several mirrors can coexist. The important part is that **coverage is scoped but
graph visibility is not** — the resolver always indexes the whole repository, so
a note in `services/api` still points at

```
## Uses
- ../../libs/shared/src/shared/log.py
```

a real, readable path rather than a dead `External: shared` entry. And
`libs/shared`'s own note reports callers in *every* package, including ones with
no mirror at all:

```
## Used by
- ../../services/api/src/app/main.py
- ../../services/billing/src/app/main.py
```

That is the monorepo question — *who breaks if I change this?* — answered from a
precomputed graph. Scoping the resolver as well as the coverage is the obvious
implementation and it silently destroys exactly this; `tests/test_scoping.py`
asserts against it.

All paths inside a note are relative to that mirror's root.

Then just work. A `PostToolUse` hook records what you edit; a `Stop` hook
re-maps the graph silently and asks for prose only on files you touched. That
loop is how coverage grows.

## Staleness

Each note stores the git blob hash of its source at last prose fill. Three
states derive from one field, so nothing can desync:

- `source_sha` absent → never filled
- present, ≠ current hash → prose is stale
- present, = current hash → clean

`verify` reports `MISSING` / `ORPHAN` / `PROSE-STALE` / `UNFILLED` and exits
non-zero on the first three — wire it into pre-commit. It does *not* fail on
`UNFILLED`, because partial prose is the expected steady state.

Graph staleness is not tracked at all: `map` fixes it mechanically, so it is
never something anyone has to think about.

## Install

Python 3, stdlib only, no dependencies, no build step.

```bash
# user-level, available in every repo
git clone https://github.com/<owner>/agent_reminiscence ~/.claude/skills/reminiscence

# or project-level, committed with the repo it serves
git clone https://github.com/<owner>/agent_reminiscence .claude/skills/reminiscence
```

Then, in the repo you want covered:

```bash
/reminiscence init
/reminiscence map
```

**Install the hooks too.** They are what makes coverage grow on its own; without
them the model degrades to filling notes by hand. They need a one-time
`settings.json` entry — see [references/setup.md](references/setup.md), which
also covers the pre-commit gate and CI wiring.

## Layout

```
SKILL.md                     verb dispatch, state machine, note rules
agents/reminiscence-filler.md   Haiku bulk-fill agent
scripts/reminiscence.py      the CLI
scripts/extractors/python.py ast parse + import resolution
hooks/                       post_tool_use.py, stop.py
references/                  note-format, fill-guide, graph-resolution,
                             comment-policy, setup
tests/                       fixtures + exact edge-set assertions
```

## Tests

```bash
python3 tests/test_extractor.py
```

Asserts the exact edge set for a `src/` layout and a flat layout, covering
level-3 relative imports, `__init__.py` re-exports, the `from a.b import c`
module-vs-symbol ambiguity, `__all__` present and absent, and a circular import.
It also asserts that inversion is **total** — `A uses B` ⟺ `B used-by A` — since
a graph that loses back-edges silently degrades traversal into search.

## Limits

Python only. Non-Python files get notes with an empty generated region; their
prose still works. Dynamic imports (`importlib.import_module`) produce no edge.
Re-exports are followed one hop — `INDEX.md` covers the definition site directly.
Details in [references/graph-resolution.md](references/graph-resolution.md).
