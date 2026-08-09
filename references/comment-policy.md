# Comment policy

Reminiscence exists so source files can stay readable for the humans who own
them. Agents left alone produce banner blocks, restated lines and redundant
docstrings; that commentary exists because the agent genuinely needed the
context, but the code is the wrong place for most of it.

"Write fewer comments" is not actionable. These lists are.

## Moves out of the code, into the note

**Banner dividers**
```python
# ============================================================
#  HELPER FUNCTIONS
# ============================================================
```
The file's structure is visible. Delete.

**Comments restating the line**
```python
count += 1  # increment the counter
```

**Redundant docstrings on trivial functions**
```python
def get_name(self):
    """Get the name."""
    return self._name
```

**Block comments narrating control flow**
```python
# First we loop through all the items, then for each item we
# check if it is valid, and if so we add it to the results list.
```

**Changelog comments**
```python
# Modified by J. Smith 2024-03-12 to handle the null case
# Previously this used the old API
```
Git knows. If the *reason* still matters, it belongs in the note's
`## Why it's like this`.

**Design-rationale essays**
Any comment over ~5 lines explaining why an approach was chosen. This is exactly
what the note's prose region is for, and it has room to be thorough there
without pushing code off the screen.

## Stays in the code

**Docstrings that are genuine API surface.** Anything a caller reads through
`help()`, an IDE hover, or Sphinx. Moving these out is a pure loss — the note is
not in the tooling path. The test is whether someone calling the function
benefits, not whether the text is "documentation".

**Why-comments anchored to a specific non-obvious line**
```python
timeout = value / 1000  # the API returns ms, not s
```
The anchor *is* the value. Relocating it to a sidecar degrades both files.

**`TODO` / `FIXME` / `HACK` with context.** These are work items attached to a
location. They belong where the work is.

**License headers, `# type: ignore`, `# noqa`, `# pragma: no cover`,
compiler and linter directives.** These are machine-readable and position-bound.

## The dividing line

Ask: **does this need to be at this line, or does it just need to exist?**

Needs to be at this line → keep it in the code.
Just needs to exist → the note, where it has room and won't cost a reader
scrolling past it forever.

## Migration is opportunistic, not a project

Do not sweep a repo stripping comments. Move commentary out when you are already
editing a file for another reason and the note is being written anyway. A
comment-stripping pass produces a large diff, no behaviour change, and real risk
of deleting something load-bearing.
