# How the graph resolves

Python only, via the stdlib `ast` module. Exact where Python itself is exact,
and explicit about where it isn't.

## Two passes

**Pass 1 — parse.** Every source file is parsed once and yields `Import` /
`ImportFrom` records (with `level` for relative imports) plus its top-level
`FunctionDef` / `AsyncFunctionDef` / `ClassDef` / assignments. `__all__` is
authoritative when present; otherwise `_`-prefixed names are dropped.

Imports nested inside functions or `TYPE_CHECKING` blocks are collected too.
They are real dependency edges even when deferred, and an agent chasing a
circular-import workaround needs to see them.

Parsing is cached in `.reminiscence/.graph.json` keyed by git blob hash, so
`map` only reparses files that actually changed.

**Pass 2 — resolve and invert.** Resolution needs the whole file set, because
`from ..services import menu_cache` is only decidable with the full tree.

## The alias index

Every file is registered under several dotted names, one per plausible source
root:

```
src/app/routes/v1/menu.py
  ->  src.app.routes.v1.menu     (repo root on the path)
  ->  app.routes.v1.menu          (src/ layout)
```

The second is derived by walking up while each ancestor directory contains an
`__init__.py`; the first non-package ancestor is the source root. Registering
every alias and taking the first hit is more robust than trying to divine the
one true layout, and it makes `src/` layouts, flat layouts and
`tests/`-run-from-root all work without configuration.

## Relative imports

`level` counts the leading dots. From `src/app/routes/v1/menu.py`:

| Statement | Base after walking up | Resolves to |
| --- | --- | --- |
| `from . import x` | `src/app/routes/v1` | `.../v1/x.py` or `.../v1/x/__init__.py` |
| `from ..models import x` | `src/app/routes` | — (no `models` there) |
| `from ...models.menu import Menu` | `src/app` | `src/app/models/menu.py` |

## `from a.b import c` is ambiguous

`c` may be a submodule or a symbol inside `a/b.py`. Both are resolved when both
exist, which matches what the import actually touches:

```python
from ...services import menu_cache
```

produces **two** edges — `services/__init__.py` (the package is executed) and
`services/menu_cache.py` (the submodule is loaded). That is not
over-reporting; both files genuinely run.

```python
from ...models import Menu
```

produces **one** edge to `models/__init__.py`, because `models/Menu.py` does not
exist so `Menu` must be a symbol. Note the real definition site is
`models/menu.py`, reachable in one more hop via that note's own `Uses` — or
directly through `INDEX.md`.

## External dependencies

Anything that resolves to no file in the repo is recorded under `External` by
top-level package name. Stdlib and third-party land together, deliberately:
knowing a file reaches for `boto3` or `subprocess` is real context, and
separating them would need a dependency manifest the extractor does not read.

## Inversion

`Used by` is the inverted edge set, and inversion is **total** — `A` listing `B`
under `Uses` always implies `B` lists `A` under `Used by`. This is asserted in
`tests/test_extractor.py` for every fixture, because a graph that loses back-edges
silently degrades traversal into search.

Inbound edges from test paths (`tests/`, `test_*.py`, `*_test.py`) are split out
into `Tested by` instead.

## Cycles

Circular imports are common and are represented faithfully — `A -> B` and
`B -> A` both appear. The fill ordering uses depth with cycle-breaking rather
than a strict topological sort, since a strict sort would simply fail.

## Known limits

These produce no edge. All are cases where the target is not statically
knowable:

- `importlib.import_module(name)` and other dynamic imports
- `__import__` with a computed name
- Star imports contribute the module edge, but individual names are not tracked
- Conditional imports resolve both branches (correct for the graph, but the note
  cannot say which one runs)
- Re-exports are followed one hop: `from .models import Menu` edges to
  `models/__init__.py`, not to the file that truly defines `Menu`. `INDEX.md`
  covers this — it maps the symbol to its definition site directly.

Non-Python source files get notes with an empty generated region. Their prose
still works, and `Related` can be filled by hand. Adding a language means adding
one extractor with `parse_file` and letting `Resolver` handle the rest.
