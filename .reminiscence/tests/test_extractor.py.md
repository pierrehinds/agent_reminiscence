---
source: tests/test_extractor.py
source_sha: 65cbd0c5fd642381b26f2c8d7d061dfa2871c11d
filled_by: main
updated: 2026-08-09
---

<!-- reminiscence:generated:start -->
## Uses
- scripts/extractors/python.py

## Used by
—

## Tested by
—

## Exports
FIXTURES, SRC_LAYOUT_USES, SRC_LAYOUT_EXTERNAL, SRC_LAYOUT_EXPORTS, FLAT_USES, failures, check, walk, run_case, main

## External
__future__, os, sys
<!-- reminiscence:generated:end -->

## Role
Guards the one property the whole design rests on: that the edge set is exact.

## Interfaces
—

## Why it's like this
Asserts exact sets rather than membership. A resolver that silently drops an
edge degrades traversal back into search; one that invents an edge sends the
agent to an irrelevant file. Both are invisible to a subset check.

The inversion assertion (`A uses B` implies `B used-by A`) exists because
`Used by` is the section that earns the design, and it is generated rather
than parsed — nothing else would catch it going wrong.

## Gotchas
Each fixture resolves in isolation. Sharing one Resolver across layouts would let `srclayout` and `flat` collide in the alias index and mask real bugs.

## Related
- [[scripts/extractors/python.py]] — the thing under test
