---
source: scripts/extractors/python.py
source_sha: b480b8ec1c6d757920f136c20bc2655f4c92b741
filled_by: main
updated: 2026-08-09
---

<!-- reminiscence:generated:start -->
## Uses
—

## Used by
- scripts/reminiscence.py

## Tested by
- tests/test_extractor.py

## Exports
RawImport, FileFacts, Resolved, parse_file, Resolver, is_test_path, read_text, collect

## External
__future__, ast, dataclasses, os, posixpath
<!-- reminiscence:generated:end -->

## Role
—

## Interfaces
—

## Why it's like this
Parse and resolve are split because resolution needs the whole
file set; `from ..services import x` is undecidable per-file.

## Gotchas
—

## Related
—
