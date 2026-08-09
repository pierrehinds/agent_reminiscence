---
name: reminiscence
description: Build and use a traversable memory graph for a codebase — a mirror tree of markdown notes at .reminiscence/<source path>.md carrying pre-resolved links to the files each source uses and is used by, so an agent navigates by computed Read instead of grep. Use when the user asks to init/map/fill reminiscence, invokes it by name, asks to set up agent memory or a code context layer for a repo, or when working in a repo that already has a .reminiscence/ directory.
version: 1.0.0
---

# Reminiscence

A parallel tree of markdown notes mirroring the source tree exactly:

```
src/app/routes/menu.py   ->   .reminiscence/src/app/routes/menu.py.md
```

The note path is **computed, never searched**: `.reminiscence/` + source path + `.md`.
One `Read` with a derived path — no `Glob`, no `Grep`.

Each note is a **routing node** first and a commentary layer second. It carries
pre-resolved links to the files this one uses and the files that use it, so you
traverse the codebase by following edges instead of guessing at import
resolution.

---

## Before any command: resolve the script

The skill runs with the working directory set to the **user's repo**, not the
skill directory, so a bare relative path will not find the script. Resolve it
once at the start of the turn and reuse the result:

```bash
for p in "$CLAUDE_PLUGIN_ROOT/scripts/reminiscence.py" \
         "$HOME/.claude/skills/reminiscence/scripts/reminiscence.py" \
         ".claude/skills/reminiscence/scripts/reminiscence.py" \
         "scripts/reminiscence.py"; do
  [ -f "$p" ] && REM="$p" && break
done; echo "${REM:?reminiscence: script not found}"
```

That covers a plugin install, a user-level skill, a project-level skill, and
running inside the skill's own repo. Every `$REM` below means that path.

The script itself does not care about the working directory — it locates the
target repo with `git rev-parse`, so it can be invoked from anywhere.

---

## The two regions of a note

This split is the core of the design. **Never blur it.**

| Region | Owner | Cost | Rule |
| --- | --- | --- | --- |
| Between `<!-- reminiscence:generated:start -->` and `:end -->` | `map` | free, exact | **Never hand-edit.** Run `map`. |
| Everything after `:end -->` | you (or the filler agent) | tokens | Never restate the code. |

Edges are derived facts. `ast` gets them right every time; a model writing them
by hand gets them wrong and they drift on the next edit.

---

## Verb dispatch

Parse the argument after `reminiscence`. No argument means bare invocation.

### `init`
Build the mirror: an empty skeleton note per source file, `_dir.md` per
directory, and gitignore entries for the scratch files. Structure only, no
content.

```bash
python3 "$REM" scaffold
```

Then tell the user how many notes were created and that `map` is the free next
step.

### `map`
Populate every generated region from the import graph, and rebuild
`.reminiscence/INDEX.md`.

```bash
python3 "$REM" map
```

Free, idempotent, no model. Safe to run at any time.

### `fill [<path|glob>]`
Bulk cold-fill of prose. **Dispatch to the `reminiscence-filler` agent, batched
by directory, one agent per directory, several in parallel.** Never fill in bulk
on the main thread — that is what the Haiku filler exists for.

```bash
python3 "$REM" unfilled --dirs
```

Each line is `<directory>\t<space-separated paths>`, already in dependency-first
order so a note can reference its neighbours'. Give each filler agent one
directory's paths **and the absolute `$REM` path** — the subagent's working
directory is the target repo, so it cannot resolve the script itself.
Resumability is free: a stamped note is a completed note, so re-running
`unfilled` after an interruption picks up exactly where it stopped.

Scope with the argument when given (`fill src/app/routes/**`); otherwise fill
everything `unfilled` reports.

### `map-and-fill [<glob>]`
`map`, then `fill`. The opt-in accelerator for a repo you want warm now.

### `status`
```bash
python3 "$REM" status
```

### bare `reminiscence`
Detect state and act:

```
not init'd            -> report, offer init. Do not run it unasked.
init'd, not mapped    -> run map silently (free), then continue
mapped                -> run the per-turn workflow below
```

**Never auto-launch a bulk `fill` from a bare invocation.** Partial prose is the
expected steady state, not a defect. Report coverage and offer.

---

## Per-turn workflow

This is the default behaviour in any repo that has a `.reminiscence/` directory,
whether or not the user typed the verb.

1. **Enter.** Before touching `src/foo.py`, read `.reminiscence/src/foo.py.md`.
   Computed path. Do not search for it.
2. **Traverse.** Follow `Uses` / `Used by` / `Tested by` by computed path, as
   deep as the task needs. Read the *note* before the *file* — the note tells
   you whether the file is even relevant, at a fraction of the tokens.
   For "where is symbol X defined?", read `.reminiscence/INDEX.md`.
3. **Edit** normally. The `PostToolUse` hook records what you touched; you do
   not need to track it.
4. **Diffuse.** At end of turn the `Stop` hook re-maps the graph silently and
   then asks you for prose on the files you edited. Write it from what you
   learned *this turn*, then:
   ```bash
   python3 "$REM" stamp <paths> --by main
   ```
   This step is how coverage grows. It is not optional bookkeeping — it is the
   mechanism.

---

## Note rules

1. **Never restate what the code says.** No signature listings, no control-flow
   narration, no "this function returns a menu". If a section has nothing real,
   leave it as `—`. A note whose prose is one `## Role` line and four em-dashes
   is **complete and correct** for an unsurprising file — its edges are the
   payload. Never pad to fill the template.
2. **Never hand-edit the generated region.** Run `map`.
3. **Anchor by symbol name, never by line number.** Line numbers rot on the
   next edit; symbol names survive refactors and are greppable.
4. **`[[wikilinks]]` use repo-relative source paths**, not note paths.
5. **Never hand-write `source_sha`.** `stamp` computes it.

What belongs in prose, concretely: why this design over the obvious one, what
was tried and failed, constraints not visible locally, ordering requirements,
footguns, bugs this file has caused, ticket links. See
[`references/fill-guide.md`](references/fill-guide.md) for worked good/bad pairs.

---

## Comment policy

Reminiscence exists so source files can stay readable for humans. When editing
code in a reminiscence repo, move agent-style bloat into the note instead of the
source: banner dividers, comments restating the line, redundant docstrings on
trivial functions, block comments narrating control flow, changelog comments,
design-rationale essays.

Keep in the code: docstrings that are genuine API surface, why-comments anchored
to a specific non-obvious line, `TODO`/`FIXME`/`HACK` with context, license
headers and linter pragmas. Full lists in
[`references/comment-policy.md`](references/comment-policy.md).

---

## Setup

Hooks are what make diffusion happen; without them the model degrades to manual
filling. Installation, `settings.json` shape, pre-commit and CI wiring are in
[`references/setup.md`](references/setup.md).

## Further reference

- [`references/note-format.md`](references/note-format.md) — frontmatter, regions, section semantics
- [`references/fill-guide.md`](references/fill-guide.md) — how to write prose worth reading
- [`references/graph-resolution.md`](references/graph-resolution.md) — how imports resolve, and the known limits
- [`references/comment-policy.md`](references/comment-policy.md)
- [`references/setup.md`](references/setup.md)
