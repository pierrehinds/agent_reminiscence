---
source: tests/test_scoping.py
source_sha: d280a23b6d14dca2b4bb3aa2cdf1caa9bfff3b32
filled_by: main
updated: 2026-08-09
---

<!-- reminiscence:generated:start -->
## Uses
—

## Used by
—

## Tested by
—

## Exports
CLI, SERVICE, failures, check, contains, run, build, read, main

## External
__future__, os, shutil, subprocess, sys, tempfile
<!-- reminiscence:generated:end -->

## Role
Guards the one invariant monorepo support rests on: coverage is scoped, graph
visibility is not.

## Interfaces
—

## Why it's like this
Drives the real CLI via subprocess instead of importing it. What is under test
is the interaction between cwd, git and the mirror — none of which a unit test
of the path helpers would touch.

Builds a throwaway git repo per run rather than committing a monorepo fixture,
because scope resolution depends on real `git ls-files` output and on walking
up a real directory tree.

## Gotchas
Asserts `External` is `—` for a cross-scope import, not merely that the edge is
present. Scoping the resolver alongside the coverage is the obvious
implementation and it fails exactly here: the edge silently becomes a bare
`External: shared` string and the link is lost.

## Related
—
