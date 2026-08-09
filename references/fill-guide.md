# Writing prose worth reading

The reader of a note is an agent that can open the source file whenever it
likes. That single fact decides everything below: **anything recoverable by
reading the file is worth zero and costs tokens.**

## The test

Before writing a line, ask: *could someone learn this by reading the file?*

If yes, delete it.

## Worked pairs

**Role**

> ❌ This module defines the `MenuCache` class and helper functions for caching
> menus.

> ✅ The only writer to the menu cache. Routes read through it; the sync job
> writes through it. Nothing else may touch the Redis keys directly.

The first restates the file listing. The second states an invariant you cannot
see from inside this file — and which a change here could break.

**Interfaces**

> ❌ `get(key: str) -> Menu | None` returns the cached menu or None.

> ✅ Returns `None` for both "miss" and "cached negative". Callers that need to
> distinguish must check `was_negative` — several have got this wrong.

The signature is already in `Exports` and in the file. The failure mode is not.

**Why it's like this**

> ❌ We use a TTL of 300 seconds for caching.

> ✅ TTL is 300s because the upstream POS pushes on a 5-minute cron — shorter
> just re-fetches identical payloads. Tried event-driven invalidation in #388;
> the POS webhook is unreliable enough that we reverted.

The first is visible one line above in the source. The second saves the next
person from re-running a failed experiment.

**Gotchas**

> ❌ Be careful when modifying this function.

> ✅ `invalidate` must run before the transaction commits, not after. Reversed
> in #501 and produced a 20-minute stale window that no test caught.

Vague caution is noise. A named failure with a shape is a warning.

## What to hunt for

Read the file and ask what would surprise a competent stranger:

- A constant with a specific non-round value — where did it come from?
- A retry, sleep, or defensive check for a case that "can't happen"
- An ordering requirement between two calls
- Duplication that looks accidental but isn't
- A public function that is unsafe to call in some state
- A dependency that seems unrelated to the file's job
- Something the file's name or location actively misrepresents
- Source comments hinting at history: "legacy", "temporary", "do not"

## Diffusion fill is different, and better

When you fill a note right after editing a file, you know things a cold pass
cannot reconstruct: the bug you just chased, the approach you tried first, the
constraint you discovered halfway through. **That is the highest-value content
in the entire layer.** Write it down while you still have it.

A cold filler reading `menu_cache.py` can describe it. Only the agent that spent
this turn debugging its TTL behaviour can say why the obvious fix doesn't work.

## Length

Short. A note over ~25 lines of prose is almost always padded. The limits in the
filler agent definition (2 sentences for Role, 6 lines for Why) are real limits,
not targets to reach.

## When to write nothing

Most files. Dataclasses, constants modules, thin `__init__.py` re-exports, plain
CRUD routes with no surprises — `## Role` plus em-dashes is the complete,
correct note. Its edges still make it a working routing node.

Filling every section on every file is the failure mode that kills the layer:
once an agent learns that notes are mostly padding, it stops reading them, and
the graph stops being traversed.
