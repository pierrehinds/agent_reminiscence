#!/usr/bin/env python3
"""Mechanical primitives behind the reminiscence skill verbs.

Nothing here calls a model. `map` owns the generated region of every note and
rewrites it from the `ast` graph; everything else is bookkeeping over note
frontmatter. The prose between the markers belongs to the fill step and is
never touched by this script.

Two path spaces, and confusing them is the easiest way to break this file:
*repo-relative* is what git and the resolver speak, *scope-relative* is what
notes contain and what an agent standing in the scope root can use directly.
Conversion happens only at the note-rendering boundary.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import posixpath
import subprocess
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from extractors import python as px  # noqa: E402

MIRROR = ".reminiscence"
# Repo-wide derived state, kept under .git/ so it is never mistaken for a
# mirror by scope discovery and never needs gitignoring.
GRAPH_CACHE = ".git/reminiscence.graph.json"
INDEX_NAME = "INDEX.md"
GEN_START = "<!-- reminiscence:generated:start -->"
GEN_END = "<!-- reminiscence:generated:end -->"

SOURCE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".rs",
    ".rb", ".java", ".kt", ".swift", ".c", ".h", ".cc", ".cpp", ".hpp", ".cs",
    ".php", ".scala", ".sh", ".sql", ".vue", ".svelte",
}

DEFAULT_IGNORES = [
    "*.min.js", "*.lock", "*.generated.*", "*_pb2.py", "*.d.ts",
    "node_modules/*", "vendor/*", "dist/*", "build/*", ".venv/*",
    f"{MIRROR}/*",
]

PROSE_SECTIONS = ["Role", "Interfaces", "Why it's like this", "Gotchas", "Related"]

SLOP_OPENERS = (
    "this function", "this file", "this module", "this class", "this method",
    "this script", "the function", "defines a function", "a function that",
    "returns the", "takes a",
)


# --------------------------------------------------------------------------
# repo and scope
# --------------------------------------------------------------------------

def repo_root() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        sys.exit("reminiscence: not inside a git repository")


def scope_prefix(root: str, explicit: str | None = None, *, creating: bool = False) -> str:
    """Repo-relative prefix of the covered subtree; '' means the whole repo.

    Without an explicit path this walks up from the working directory looking
    for the nearest `.reminiscence/`, the way git finds `.git`. That makes the
    terminal's location the default scope, so a monorepo can carry one mirror
    per package without any configuration.

    Falling back to the repo root when no mirror is found is only safe while
    *creating* one. For every other verb that fallback silently invents a
    whole-repo scope — running `map` from the root of a monorepo scoped to one
    package would scaffold a second mirror over every package in the tree.
    """
    if explicit is not None:
        rel = os.path.relpath(os.path.abspath(explicit), root).replace(os.sep, "/")
        if rel.startswith(".."):
            sys.exit(f"reminiscence: {explicit} is outside the repository")
        return "" if rel == "." else rel

    cursor = os.path.abspath(os.getcwd())
    while True:
        if os.path.isdir(os.path.join(cursor, MIRROR)):
            rel = os.path.relpath(cursor, root).replace(os.sep, "/")
            return "" if rel == "." else rel
        if cursor == root or cursor == os.path.dirname(cursor):
            break
        cursor = os.path.dirname(cursor)

    if creating:
        return ""

    existing = other_mirrors(root)
    if len(existing) == 1:
        return existing[0]
    if not existing:
        sys.exit(
            "reminiscence: no mirror found at or above this directory.\n"
            "  run `reminiscence init` here, or `init --scope <folder>`"
        )
    listed = "\n".join(f"    {m or '(repo root)'}" for m in existing)
    sys.exit(
        "reminiscence: several mirrors in this repo and none above the working "
        f"directory:\n{listed}\n  pass --scope <folder>, or cd into one"
    )


def scope_for_path(root: str, repo_rel: str) -> str | None:
    """Which mirror owns this file: nearest `.reminiscence/` at or above it.

    Hooks must use this rather than the cwd — one session sitting at a monorepo
    root can edit files belonging to several different mirrors in a single turn.
    """
    cursor = os.path.dirname(os.path.join(root, repo_rel))
    while True:
        if os.path.isdir(os.path.join(cursor, MIRROR)):
            rel = os.path.relpath(cursor, root).replace(os.sep, "/")
            return "" if rel == "." else rel
        if cursor == root or cursor == os.path.dirname(cursor):
            return None
        cursor = os.path.dirname(cursor)


def in_scope(path: str, prefix: str) -> bool:
    return True if not prefix else path.startswith(f"{prefix}/")


def to_scope(path: str, prefix: str) -> str:
    """Repo-relative -> scope-relative. Outside the scope yields `../`."""
    if not prefix:
        return path
    return posixpath.relpath(path, prefix)


def to_repo(path: str, prefix: str) -> str:
    if not prefix:
        return posixpath.normpath(path)
    return posixpath.normpath(posixpath.join(prefix, path))


def tracked_files(root: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True, check=True,
    )
    return sorted({line for line in out.stdout.splitlines() if line})


def blob_sha(root: str, path: str) -> str | None:
    """Git's own blob hash, computed in-process to keep `map` subprocess-free."""
    try:
        with open(os.path.join(root, path), "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def load_ignores(root: str, prefix: str) -> list[str]:
    patterns = list(DEFAULT_IGNORES)
    path = os.path.join(root, prefix, ".reminiscenceignore")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
    return patterns


def ignored(path: str, patterns: list[str]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
        if pattern.endswith("/*") and path.startswith(pattern[:-1]):
            return True
        if "/" not in pattern and fnmatch.fnmatch(posixpath.basename(path), pattern):
            return True
    return False


def sources(root: str, prefix: str) -> list[str]:
    """Repo-relative source files that get notes — the coverage scope."""
    patterns = load_ignores(root, prefix)
    out = []
    for path in tracked_files(root):
        if posixpath.splitext(path)[1] not in SOURCE_EXTS:
            continue
        if not in_scope(path, prefix):
            continue
        if ignored(to_scope(path, prefix), patterns):
            continue
        out.append(path)
    return out


def visible_python(root: str) -> list[str]:
    """Every Python file in the repo — the graph's visibility, not its coverage.

    Deliberately unscoped. A note in services/api must still resolve an import
    of libs/shared to a real path; scoping this too is what turns a real edge
    into a dead `External` string.
    """
    return [
        p for p in tracked_files(root)
        if posixpath.splitext(p)[1] in {".py", ".pyi"}
        and not p.startswith(f"{MIRROR}/") and f"/{MIRROR}/" not in p
    ]


def note_path(source: str, prefix: str) -> str:
    """Repo-relative path of the note for a repo-relative source path."""
    return posixpath.join(prefix, MIRROR, to_scope(source, prefix)) + ".md"


def mirror_root(prefix: str) -> str:
    return posixpath.join(prefix, MIRROR) if prefix else MIRROR


# --------------------------------------------------------------------------
# note file format
# --------------------------------------------------------------------------

def parse_note(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, text[end + 5:]


def render_note(meta: dict[str, str], body: str) -> str:
    order = ["source", "source_sha", "filled_by", "updated"]
    keys = [k for k in order if k in meta] + [k for k in meta if k not in order]
    lines = "\n".join(f"{k}: {meta[k]}" for k in keys)
    return f"---\n{lines}\n---\n{body}"


def split_generated(body: str) -> tuple[str, str, str]:
    start = body.find(GEN_START)
    if start == -1:
        return body, "", ""
    end = body.find(GEN_END, start)
    if end == -1:
        return body, "", ""
    return body[:start], body[start + len(GEN_START):end], body[end + len(GEN_END):]


def read_note(root: str, path: str) -> tuple[dict[str, str], str] | None:
    full = os.path.join(root, path)
    if not os.path.exists(full):
        return None
    with open(full, encoding="utf-8") as handle:
        return parse_note(handle.read())


def write_note(root: str, path: str, meta: dict[str, str], body: str) -> bool:
    """Write only when content actually changes, so `map` stays idempotent."""
    full = os.path.join(root, path)
    text = render_note(meta, body)
    if os.path.exists(full):
        with open(full, encoding="utf-8") as handle:
            if handle.read() == text:
                return False
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(text)
    return True


def skeleton_tail() -> str:
    return "\n\n".join(f"## {name}\n—" for name in PROSE_SECTIONS) + "\n"


def skeleton_body() -> str:
    return f"\n{GEN_START}\n{GEN_END}\n\n{skeleton_tail()}"


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------

def build_graph(root: str, force: set[str] | None = None) -> dict:
    """Repo-wide graph, in repo-relative paths. Scoping happens at render time."""
    py = visible_python(root)
    cache = {}
    cache_path = os.path.join(root, GRAPH_CACHE)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as handle:
                cache = json.load(handle)
        except (OSError, json.JSONDecodeError):
            cache = {}

    force = force or set()
    facts: dict[str, px.FileFacts] = {}
    fresh: dict[str, dict] = {}

    for path in py:
        sha = blob_sha(root, path)
        hit = cache.get(path)
        if hit and hit.get("sha") == sha and path not in force:
            facts[path] = px.FileFacts(
                path=path,
                imports=[px.RawImport(**i) for i in hit["imports"]],
                exports=hit["exports"],
            )
        else:
            try:
                facts[path] = px.parse_file(path, px.read_text(os.path.join(root, path)))
            except OSError as exc:
                facts[path] = px.FileFacts(path=path, parse_error=str(exc))
        entry = facts[path]
        fresh[path] = {
            "sha": sha,
            "imports": [vars(i) for i in entry.imports],
            "exports": entry.exports,
        }

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as handle:
        json.dump(fresh, handle, indent=0, sort_keys=True)

    resolver = px.Resolver(list(facts))
    uses: dict[str, list[str]] = {}
    external: dict[str, list[str]] = {}
    for path, entry in facts.items():
        res = resolver.resolve(entry)
        uses[path] = res.uses
        external[path] = res.external

    used_by: dict[str, list[str]] = {}
    for path, targets in uses.items():
        for target in targets:
            used_by.setdefault(target, []).append(path)
    for key in used_by:
        used_by[key] = sorted(set(used_by[key]))

    return {
        "uses": uses,
        "used_by": used_by,
        "external": external,
        "exports": {p: facts[p].exports for p in facts},
    }


def generated_block(source: str, graph: dict, prefix: str) -> str:
    uses = graph["uses"].get(source, [])
    used_by = graph["used_by"].get(source, [])
    exports = graph["exports"].get(source, [])
    external = graph["external"].get(source, [])

    tests = [p for p in used_by if px.is_test_path(p)]
    callers = [p for p in used_by if not px.is_test_path(p)]

    def block(title: str, items: list[str], inline: bool = False, scope: bool = False) -> str:
        if scope:
            items = [to_scope(i, prefix) for i in items]
        if not items:
            return f"## {title}\n—\n"
        if inline:
            return f"## {title}\n{', '.join(items)}\n"
        return f"## {title}\n" + "\n".join(f"- {i}" for i in items) + "\n"

    parts = [
        block("Uses", uses, scope=True),
        block("Used by", callers, scope=True),
        block("Tested by", tests, scope=True),
        block("Exports", exports, inline=True),
        block("External", external, inline=True),
    ]
    return "\n" + "\n".join(parts)


def rewrite_notes(root: str, prefix: str, srcs: list[str], graph: dict) -> int:
    changed = 0
    for source in srcs:
        path = note_path(source, prefix)
        parsed = read_note(root, path)
        if parsed is None:
            meta, body = {"source": to_scope(source, prefix)}, skeleton_body()
        else:
            meta, body = parsed
            meta.setdefault("source", to_scope(source, prefix))
        before, _, after = split_generated(body)
        if not after and GEN_START not in body:
            before, after = "\n", "\n\n" + skeleton_tail()
        new_body = f"{before}{GEN_START}{generated_block(source, graph, prefix)}{GEN_END}{after}"
        if write_note(root, path, meta, new_body):
            changed += 1
    return changed


def write_index(root: str, prefix: str, graph: dict, srcs: list[str]) -> None:
    covered = set(srcs)
    symbols: dict[str, list[str]] = {}
    for source, names in graph["exports"].items():
        for name in names:
            symbols.setdefault(name, []).append(source)

    lines = [
        "# Symbol index",
        "",
        "Generated by `reminiscence map`. Resolves a symbol to the file that",
        "defines it, so \"where is X?\" is one Read instead of a repo-wide grep.",
        "",
        "Paths are relative to this mirror's root. Entries marked `(outside scope)`",
        "resolve to real files that have no note — read the source directly.",
        "",
    ]
    for name in sorted(symbols):
        for source in sorted(symbols[name]):
            mark = "" if source in covered else "  (outside scope)"
            lines.append(f"- `{name}` — {to_scope(source, prefix)}{mark}")
    lines.append("")

    full = os.path.join(root, mirror_root(prefix), INDEX_NAME)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    text = "\n".join(lines)
    if os.path.exists(full):
        with open(full, encoding="utf-8") as handle:
            if handle.read() == text:
                return
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(text)


# --------------------------------------------------------------------------
# audit
# --------------------------------------------------------------------------

def collect_notes(root: str, prefix: str) -> list[str]:
    base = os.path.join(root, mirror_root(prefix))
    skip = {INDEX_NAME, "README.md", "_dir.md"}
    out = []
    for dirpath, _dirs, files in os.walk(base):
        for name in files:
            if not name.endswith(".md") or name in skip:
                continue
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(out)


def audit(root: str, prefix: str) -> dict[str, list[str]]:
    srcs = sources(root, prefix)
    have = set()
    result = {"MISSING": [], "ORPHAN": [], "UNFILLED": [], "PROSE-STALE": []}

    for path in collect_notes(root, prefix):
        parsed = read_note(root, path)
        if parsed is None:
            continue
        meta, _ = parsed
        scoped = meta.get("source")
        if not scoped:
            continue
        source = to_repo(scoped, prefix)
        have.add(source)
        if not os.path.exists(os.path.join(root, source)):
            result["ORPHAN"].append(path)
            continue
        sha = meta.get("source_sha")
        if not sha:
            result["UNFILLED"].append(source)
        elif sha != blob_sha(root, source):
            result["PROSE-STALE"].append(source)

    result["MISSING"] = [s for s in srcs if s not in have]
    for key in result:
        result[key].sort()
    return result


def lint(root: str, prefix: str) -> list[str]:
    findings = []
    for path in collect_notes(root, prefix):
        parsed = read_note(root, path)
        if parsed is None:
            continue
        meta, body = parsed
        if not meta.get("source_sha"):
            continue
        _, generated, after = split_generated(body)
        exported = set()
        for chunk in generated.split("## Exports\n")[1:]:
            exported = {s.strip() for s in chunk.splitlines()[0].split(",") if s.strip()}
        prose = after.lower()
        for opener in SLOP_OPENERS:
            if f"\n{opener}" in prose or prose.strip().startswith(opener):
                findings.append(f"{path}: prose opens by restating code (\"{opener}...\")")
                break
        if len(exported) > 1 and all(n.lower() in prose for n in exported):
            findings.append(f"{path}: prose re-lists every exported symbol")
    return sorted(findings)


# --------------------------------------------------------------------------
# verbs
# --------------------------------------------------------------------------

def resolve(args) -> tuple[str, str]:
    root = repo_root()
    return root, scope_prefix(root, getattr(args, "scope", None))


def cmd_path(args) -> int:
    root, prefix = resolve(args)
    source = to_repo(args.source, prefix) if not args.source.startswith(prefix or "\0") else args.source
    print(to_scope(note_path(source, prefix), prefix))
    return 0


def cmd_sources(args) -> int:
    root, prefix = resolve(args)
    for path in sources(root, prefix):
        print(to_scope(path, prefix))
    return 0


def cmd_scaffold(args) -> int:
    root = repo_root()
    where = args.folder or args.scope or os.getcwd()
    prefix = scope_prefix(root, where, creating=True)
    srcs = sources(root, prefix)
    created = 0

    for source in srcs:
        path = note_path(source, prefix)
        if os.path.exists(os.path.join(root, path)):
            continue
        write_note(root, path, {"source": to_scope(source, prefix)}, skeleton_body())
        created += 1

    for directory in sorted({posixpath.dirname(to_scope(s, prefix)) for s in srcs}):
        path = posixpath.join(mirror_root(prefix), directory, "_dir.md")
        if os.path.exists(os.path.join(root, path)):
            continue
        label = directory or "(scope root)"
        write_note(
            root, path, {"source_dir": directory or "."},
            f"\n# {label}\n\n## Role\n—\n\n## Why it's like this\n—\n\n## Conventions\n—\n",
        )
        created += 1

    readme = os.path.join(root, mirror_root(prefix), "README.md")
    template = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "templates", "repo-readme.md",
    )
    if not os.path.exists(readme) and os.path.exists(template):
        os.makedirs(os.path.dirname(readme), exist_ok=True)
        with open(template, encoding="utf-8") as src, open(readme, "w", encoding="utf-8") as dst:
            dst.write(src.read())
        created += 1

    gitignore = os.path.join(root, ".gitignore")
    # Only .dirty is per-scope; the graph cache and stop state are repo-wide
    # and live under .git/, which needs no gitignore entry.
    needed = [f"{mirror_root(prefix)}/.dirty"]
    existing = ""
    if os.path.exists(gitignore):
        with open(gitignore, encoding="utf-8") as handle:
            existing = handle.read()
    missing = [line for line in needed if line not in existing]
    if missing:
        with open(gitignore, "a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write("\n".join(missing) + "\n")

    where = prefix or "(repo root)"
    print(f"scaffolded {created} notes for {len(srcs)} sources, scope: {where}")
    return 0


def cmd_map(args) -> int:
    root, prefix = resolve(args)
    srcs = sources(root, prefix)
    graph = build_graph(root, force={to_repo(p, prefix) for p in (args.paths or [])})
    changed = rewrite_notes(root, prefix, srcs, graph)
    write_index(root, prefix, graph, srcs)
    print(f"mapped {len(srcs)} sources, {changed} notes updated, scope: {prefix or '(repo root)'}")
    return 0


def cmd_verify(args) -> int:
    root, prefix = resolve(args)
    result = audit(root, prefix)
    findings = lint(root, prefix) if args.lint else []

    if args.json:
        print(json.dumps({**result, "LINT": findings}, indent=2))
    else:
        for key in ("MISSING", "ORPHAN", "PROSE-STALE", "UNFILLED"):
            for item in result[key]:
                print(f"{key}\t{to_scope(item, prefix)}")
        for finding in findings:
            print(f"LINT\t{finding}")

    blocking = result["MISSING"] + result["ORPHAN"] + result["PROSE-STALE"] + findings
    return 1 if blocking else 0


def cmd_unfilled(args) -> int:
    root, prefix = resolve(args)
    result = audit(root, prefix)
    pending = result["UNFILLED"] + result["PROSE-STALE"]
    if not pending:
        return 0

    graph = build_graph(root)
    ordered = topological(pending, graph)
    if args.dirs:
        grouped: dict[str, list[str]] = {}
        for source in ordered:
            scoped = to_scope(source, prefix)
            grouped.setdefault(posixpath.dirname(scoped), []).append(scoped)
        for directory, items in grouped.items():
            print(f"{directory or '.'}\t{' '.join(items)}")
    else:
        for source in ordered:
            print(to_scope(source, prefix))
    return 0


def topological(pending: list[str], graph: dict) -> list[str]:
    """Dependencies first, so a note can reference its neighbours'.

    Cycles are real in Python, so this is a depth-ordering with cycle-breaking
    rather than a strict topological sort, which would simply fail.
    """
    target = set(pending)
    depth: dict[str, int] = {}

    def walk(node: str, stack: frozenset) -> int:
        if node in depth:
            return depth[node]
        if node in stack:
            return 0
        deps = [d for d in graph["uses"].get(node, []) if d in target]
        depth[node] = 1 + max((walk(d, stack | {node}) for d in deps), default=-1)
        return depth[node]

    for node in pending:
        walk(node, frozenset())
    return sorted(pending, key=lambda n: (depth.get(n, 0), n))


def cmd_stamp(args) -> int:
    root, prefix = resolve(args)
    stamped = []
    for given in args.sources:
        source = to_repo(given, prefix)
        path = note_path(source, prefix)
        parsed = read_note(root, path)
        if parsed is None:
            print(f"reminiscence: no note for {given}", file=sys.stderr)
            continue
        meta, body = parsed
        sha = blob_sha(root, source)
        if sha is None:
            print(f"reminiscence: cannot read {given}", file=sys.stderr)
            continue
        meta["source"] = to_scope(source, prefix)
        meta["source_sha"] = sha
        meta["filled_by"] = args.by
        meta["updated"] = date.today().isoformat()
        write_note(root, path, meta, body)
        stamped.append(source)

    drop_dirty(root, prefix, stamped)
    print(f"stamped {len(stamped)} notes ({args.by})")
    return 0


def drop_dirty(root: str, prefix: str, done: list[str]) -> None:
    full = os.path.join(root, mirror_root(prefix), ".dirty")
    if not os.path.exists(full):
        return
    with open(full, encoding="utf-8") as handle:
        remaining = {l.strip() for l in handle if l.strip()} - set(done)
    if remaining:
        with open(full, "w", encoding="utf-8") as handle:
            handle.write("\n".join(sorted(remaining)) + "\n")
    else:
        os.remove(full)


def cmd_dirty(args) -> int:
    root, prefix = resolve(args)
    full = os.path.join(root, mirror_root(prefix), ".dirty")
    if not os.path.exists(full):
        return 0
    with open(full, encoding="utf-8") as handle:
        for line in sorted({l.strip() for l in handle if l.strip()}):
            print(to_scope(line, prefix))
    return 0


def cmd_status(args) -> int:
    root = repo_root()
    prefix = scope_prefix(root, getattr(args, "scope", None))
    if not os.path.isdir(os.path.join(root, mirror_root(prefix))):
        print(f"state: not initialised  (would scope to: {prefix or '(repo root)'})")
        print("run: reminiscence init")
        return 2

    srcs = sources(root, prefix)
    result = audit(root, prefix)
    notes = len(srcs) - len(result["MISSING"])
    unfilled, stale = len(result["UNFILLED"]), len(result["PROSE-STALE"])

    print(f"scope       {prefix or '(repo root)'}")
    print(f"sources     {len(srcs)}")
    print(f"notes       {notes}" + (f"  ({len(result['MISSING'])} missing)" if result["MISSING"] else ""))
    print(f"mapped      {'yes' if os.path.exists(os.path.join(root, GRAPH_CACHE)) else 'no'}")
    print(f"filled      {notes - unfilled - stale}/{notes}"
          + (f"  ({stale} stale, {unfilled} never filled)" if stale or unfilled else ""))
    if result["ORPHAN"]:
        print(f"orphans     {len(result['ORPHAN'])}  (run: reminiscence prune)")

    others = [p for p in other_mirrors(root) if p != prefix]
    if others:
        print(f"other scopes in this repo: {', '.join(o or '(repo root)' for o in others)}")
    return 0


def other_mirrors(root: str) -> list[str]:
    found = []
    for dirpath, dirs, _files in os.walk(root):
        if ".git" in dirs:
            dirs.remove(".git")
        if MIRROR in dirs:
            rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
            found.append("" if rel == "." else rel)
            dirs.remove(MIRROR)
    return sorted(found)


def cmd_scopes(args) -> int:
    root = repo_root()
    for prefix in other_mirrors(root):
        print(prefix or "(repo root)")
    return 0


def cmd_prune(args) -> int:
    root, prefix = resolve(args)
    removed = 0
    for path in collect_notes(root, prefix):
        parsed = read_note(root, path)
        if parsed is None:
            continue
        meta, _ = parsed
        scoped = meta.get("source")
        if scoped and not os.path.exists(os.path.join(root, to_repo(scoped, prefix))):
            os.remove(os.path.join(root, path))
            removed += 1
    print(f"pruned {removed} orphan notes")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="reminiscence")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def add(name, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument("--scope", default=None,
                       help="folder to operate on (default: nearest .reminiscence/ above cwd)")
        return p

    p = add("path"); p.add_argument("source"); p.set_defaults(fn=cmd_path)
    p = add("sources"); p.set_defaults(fn=cmd_sources)
    p = add("scaffold")
    p.add_argument("folder", nargs="?", default=None,
                   help="folder to cover (default: cwd); same as --scope")
    p.set_defaults(fn=cmd_scaffold)
    p = add("map"); p.add_argument("paths", nargs="*"); p.set_defaults(fn=cmd_map)
    p = add("unfilled"); p.add_argument("--dirs", action="store_true"); p.set_defaults(fn=cmd_unfilled)
    p = add("verify")
    p.add_argument("--json", action="store_true"); p.add_argument("--lint", action="store_true")
    p.set_defaults(fn=cmd_verify)
    p = add("stamp")
    p.add_argument("sources", nargs="+"); p.add_argument("--by", default="main", choices=["main", "haiku"])
    p.set_defaults(fn=cmd_stamp)
    p = add("dirty"); p.set_defaults(fn=cmd_dirty)
    p = add("status"); p.set_defaults(fn=cmd_status)
    p = add("prune"); p.set_defaults(fn=cmd_prune)
    p = sub.add_parser("scopes"); p.set_defaults(fn=cmd_scopes)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
