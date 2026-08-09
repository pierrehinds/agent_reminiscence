#!/usr/bin/env python3
"""Mechanical primitives behind the reminiscence skill verbs.

Nothing here calls a model. `map` owns the generated region of every note and
rewrites it from the `ast` graph; everything else is bookkeeping over note
frontmatter. The prose between the markers belongs to the fill step and is
never touched by this script.
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
DIRTY = f"{MIRROR}/.dirty"
GRAPH_CACHE = f"{MIRROR}/.graph.json"
INDEX = f"{MIRROR}/INDEX.md"
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
# repo plumbing
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


def tracked_files(root: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=root, capture_output=True, text=True, check=True,
    )
    return sorted({line for line in out.stdout.splitlines() if line})


def blob_sha(root: str, path: str) -> str | None:
    """Git's own blob hash, computed in-process to keep `map` subprocess-free."""
    full = os.path.join(root, path)
    try:
        with open(full, "rb") as handle:
            data = handle.read()
    except OSError:
        return None
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def load_ignores(root: str) -> list[str]:
    patterns = list(DEFAULT_IGNORES)
    path = os.path.join(root, ".reminiscenceignore")
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


def sources(root: str) -> list[str]:
    patterns = load_ignores(root)
    out = []
    for path in tracked_files(root):
        if posixpath.splitext(path)[1] not in SOURCE_EXTS:
            continue
        if ignored(path, patterns):
            continue
        out.append(path)
    return out


def note_path(source: str) -> str:
    return f"{MIRROR}/{source}.md"


def dir_note_path(directory: str) -> str:
    return posixpath.join(MIRROR, directory, "_dir.md") if directory else f"{MIRROR}/_dir.md"


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
    """Return (before, generated, after). Missing markers yield an empty middle."""
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


def skeleton_body() -> str:
    sections = "\n\n".join(f"## {name}\n—" for name in PROSE_SECTIONS)
    return f"\n{GEN_START}\n{GEN_END}\n\n{sections}\n"


# --------------------------------------------------------------------------
# graph
# --------------------------------------------------------------------------

def build_graph(root: str, srcs: list[str], force: set[str] | None = None) -> dict:
    py = [p for p in srcs if p.endswith((".py", ".pyi"))]
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

    used_by: dict[str, list[str]] = {p: [] for p in srcs}
    for path, targets in uses.items():
        for target in targets:
            used_by.setdefault(target, []).append(path)
    for key in used_by:
        used_by[key] = sorted(set(used_by[key]))

    exports = {p: facts[p].exports for p in facts}
    return {"uses": uses, "used_by": used_by, "external": external, "exports": exports}


def generated_block(source: str, graph: dict) -> str:
    uses = graph["uses"].get(source, [])
    used_by = graph["used_by"].get(source, [])
    exports = graph["exports"].get(source, [])
    external = graph["external"].get(source, [])

    tests = [p for p in used_by if px.is_test_path(p)]
    callers = [p for p in used_by if not px.is_test_path(p)]

    def block(title: str, items: list[str], inline: bool = False) -> str:
        if not items:
            return f"## {title}\n—\n"
        if inline:
            return f"## {title}\n{', '.join(items)}\n"
        listed = "\n".join(f"- {i}" for i in items)
        return f"## {title}\n{listed}\n"

    parts = [
        block("Uses", uses),
        block("Used by", callers),
        block("Tested by", tests),
        block("Exports", exports, inline=True),
        block("External", external, inline=True),
    ]
    return "\n" + "\n".join(parts)


# --------------------------------------------------------------------------
# verbs
# --------------------------------------------------------------------------

def cmd_path(args) -> int:
    print(note_path(args.source))
    return 0


def cmd_sources(args) -> int:
    for path in sources(repo_root()):
        print(path)
    return 0


def cmd_scaffold(args) -> int:
    root = repo_root()
    srcs = sources(root)
    created = 0
    for source in srcs:
        path = note_path(source)
        if os.path.exists(os.path.join(root, path)):
            continue
        write_note(root, path, {"source": source}, skeleton_body())
        created += 1

    dirs = sorted({posixpath.dirname(s) for s in srcs})
    for directory in dirs:
        path = dir_note_path(directory)
        if os.path.exists(os.path.join(root, path)):
            continue
        label = directory or "(repo root)"
        body = (
            f"\n# {label}\n\n## Role\n—\n\n## Why it's like this\n—\n\n"
            "## Conventions\n—\n"
        )
        write_note(root, path, {"source_dir": directory or "."}, body)
        created += 1

    readme = os.path.join(root, MIRROR, "README.md")
    if not os.path.exists(readme):
        template = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "templates", "repo-readme.md",
        )
        if os.path.exists(template):
            os.makedirs(os.path.dirname(readme), exist_ok=True)
            with open(template, encoding="utf-8") as src, open(readme, "w", encoding="utf-8") as dst:
                dst.write(src.read())
            created += 1

    gitignore = os.path.join(root, ".gitignore")
    needed = [f"{MIRROR}/.dirty", f"{MIRROR}/.graph.json", f"{MIRROR}/.stop_state"]
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

    print(f"scaffolded {created} notes for {len(srcs)} sources")
    return 0


def cmd_map(args) -> int:
    root = repo_root()
    srcs = sources(root)
    graph = build_graph(root, srcs, force=set(args.paths or []))

    changed = 0
    for source in srcs:
        path = note_path(source)
        parsed = read_note(root, path)
        if parsed is None:
            meta, body = {"source": source}, skeleton_body()
        else:
            meta, body = parsed
            meta.setdefault("source", source)

        before, _, after = split_generated(body)
        if not after and GEN_START not in body:
            before, after = "\n", body if body.strip() else skeleton_body_tail()
        new_body = f"{before}{GEN_START}{generated_block(source, graph)}{GEN_END}{after}"
        if write_note(root, path, meta, new_body):
            changed += 1

    write_index(root, graph, srcs)
    print(f"mapped {len(srcs)} sources, {changed} notes updated")
    return 0


def skeleton_body_tail() -> str:
    return "\n\n" + "\n\n".join(f"## {name}\n—" for name in PROSE_SECTIONS) + "\n"


def write_index(root: str, graph: dict, srcs: list[str]) -> None:
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
    ]
    for name in sorted(symbols):
        for source in sorted(symbols[name]):
            lines.append(f"- `{name}` — {source}")
    lines.append("")
    full = os.path.join(root, INDEX)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    text = "\n".join(lines)
    if os.path.exists(full):
        with open(full, encoding="utf-8") as handle:
            if handle.read() == text:
                return
    with open(full, "w", encoding="utf-8") as handle:
        handle.write(text)


def collect_notes(root: str) -> list[str]:
    base = os.path.join(root, MIRROR)
    out = []
    for dirpath, _dirs, files in os.walk(base):
        for name in files:
            if not name.endswith(".md") or name == "_dir.md":
                continue
            full = os.path.join(dirpath, name)
            out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(p for p in out if p not in (INDEX, f"{MIRROR}/README.md"))


def audit(root: str) -> dict[str, list[str]]:
    srcs = sources(root)
    have_notes = set()
    result = {"MISSING": [], "ORPHAN": [], "UNFILLED": [], "PROSE-STALE": []}

    for path in collect_notes(root):
        parsed = read_note(root, path)
        if parsed is None:
            continue
        meta, _ = parsed
        source = meta.get("source")
        if not source:
            continue
        have_notes.add(source)
        if not os.path.exists(os.path.join(root, source)):
            result["ORPHAN"].append(path)
            continue
        sha = meta.get("source_sha")
        if not sha:
            result["UNFILLED"].append(source)
        elif sha != blob_sha(root, source):
            result["PROSE-STALE"].append(source)

    result["MISSING"] = [s for s in srcs if s not in have_notes]
    for key in result:
        result[key].sort()
    return result


def lint(root: str) -> list[str]:
    findings = []
    for path in collect_notes(root):
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
        if exported and len(exported) > 1:
            named = sum(1 for name in exported if name.lower() in prose)
            if named == len(exported):
                findings.append(f"{path}: prose re-lists every exported symbol")
    return sorted(findings)


def cmd_verify(args) -> int:
    root = repo_root()
    result = audit(root)
    findings = lint(root) if args.lint else []

    if args.json:
        print(json.dumps({**result, "LINT": findings}, indent=2))
    else:
        for key in ("MISSING", "ORPHAN", "PROSE-STALE", "UNFILLED"):
            for item in result[key]:
                print(f"{key}\t{item}")
        for finding in findings:
            print(f"LINT\t{finding}")

    blocking = result["MISSING"] + result["ORPHAN"] + result["PROSE-STALE"] + findings
    return 1 if blocking else 0


def cmd_unfilled(args) -> int:
    root = repo_root()
    result = audit(root)
    pending = result["UNFILLED"] + result["PROSE-STALE"]
    if not pending:
        return 0

    graph = build_graph(root, sources(root))
    ordered = topological(pending, graph)
    if args.dirs:
        seen: dict[str, list[str]] = {}
        for source in ordered:
            seen.setdefault(posixpath.dirname(source), []).append(source)
        for directory, items in seen.items():
            print(f"{directory or '.'}\t{' '.join(items)}")
    else:
        for source in ordered:
            print(source)
    return 0


def topological(pending: list[str], graph: dict) -> list[str]:
    """Dependencies first, so a note can reference its neighbours' notes.

    Cycles are real in Python (see the fixtures), so this is a depth-ordering
    with cycle-breaking rather than a strict topological sort.
    """
    target = set(pending)
    depth: dict[str, int] = {}

    def resolve(node: str, stack: frozenset) -> int:
        if node in depth:
            return depth[node]
        if node in stack:
            return 0
        deps = [d for d in graph["uses"].get(node, []) if d in target]
        value = 1 + max((resolve(d, stack | {node}) for d in deps), default=-1)
        depth[node] = value
        return value

    for node in pending:
        resolve(node, frozenset())
    return sorted(pending, key=lambda n: (depth.get(n, 0), n))


def cmd_stamp(args) -> int:
    root = repo_root()
    stamped = []
    for source in args.sources:
        path = note_path(source)
        parsed = read_note(root, path)
        if parsed is None:
            print(f"reminiscence: no note for {source}", file=sys.stderr)
            continue
        meta, body = parsed
        sha = blob_sha(root, source)
        if sha is None:
            print(f"reminiscence: cannot read {source}", file=sys.stderr)
            continue
        meta["source"] = source
        meta["source_sha"] = sha
        meta["filled_by"] = args.by
        meta["updated"] = date.today().isoformat()
        write_note(root, path, meta, body)
        stamped.append(source)

    drop_dirty(root, stamped)
    print(f"stamped {len(stamped)} notes ({args.by})")
    return 0


def drop_dirty(root: str, done: list[str]) -> None:
    full = os.path.join(root, DIRTY)
    if not os.path.exists(full):
        return
    with open(full, encoding="utf-8") as handle:
        remaining = [line.strip() for line in handle if line.strip() not in done and line.strip()]
    if remaining:
        with open(full, "w", encoding="utf-8") as handle:
            handle.write("\n".join(sorted(set(remaining))) + "\n")
    else:
        os.remove(full)


def cmd_dirty(args) -> int:
    root = repo_root()
    full = os.path.join(root, DIRTY)
    if not os.path.exists(full):
        return 0
    with open(full, encoding="utf-8") as handle:
        for line in sorted({l.strip() for l in handle if l.strip()}):
            print(line)
    return 0


def cmd_status(args) -> int:
    root = repo_root()
    if not os.path.isdir(os.path.join(root, MIRROR)):
        print("state: not initialised")
        print("run: reminiscence init")
        return 2

    srcs = sources(root)
    result = audit(root)
    notes = len(srcs) - len(result["MISSING"])
    unfilled = len(result["UNFILLED"])
    stale = len(result["PROSE-STALE"])
    filled = notes - unfilled - stale

    mapped = os.path.exists(os.path.join(root, GRAPH_CACHE))
    print(f"sources     {len(srcs)}")
    print(f"notes       {notes}" + (f"  ({len(result['MISSING'])} missing)" if result["MISSING"] else ""))
    print(f"mapped      {'yes' if mapped else 'no'}")
    print(f"filled      {filled}/{notes}" + (f"  ({stale} stale, {unfilled} never filled)" if stale or unfilled else ""))
    if result["ORPHAN"]:
        print(f"orphans     {len(result['ORPHAN'])}  (run: reminiscence prune)")
    return 0


def cmd_prune(args) -> int:
    root = repo_root()
    removed = 0
    for path in collect_notes(root):
        parsed = read_note(root, path)
        if parsed is None:
            continue
        meta, _ = parsed
        source = meta.get("source")
        if source and not os.path.exists(os.path.join(root, source)):
            os.remove(os.path.join(root, path))
            removed += 1
    print(f"pruned {removed} orphan notes")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="reminiscence")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("path"); p.add_argument("source"); p.set_defaults(fn=cmd_path)
    p = sub.add_parser("sources"); p.set_defaults(fn=cmd_sources)
    p = sub.add_parser("scaffold"); p.set_defaults(fn=cmd_scaffold)
    p = sub.add_parser("map"); p.add_argument("paths", nargs="*"); p.set_defaults(fn=cmd_map)
    p = sub.add_parser("unfilled"); p.add_argument("--dirs", action="store_true"); p.set_defaults(fn=cmd_unfilled)
    p = sub.add_parser("verify")
    p.add_argument("--json", action="store_true"); p.add_argument("--lint", action="store_true")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("stamp")
    p.add_argument("sources", nargs="+"); p.add_argument("--by", default="main", choices=["main", "haiku"])
    p.set_defaults(fn=cmd_stamp)
    p = sub.add_parser("dirty"); p.set_defaults(fn=cmd_dirty)
    p = sub.add_parser("status"); p.set_defaults(fn=cmd_status)
    p = sub.add_parser("prune"); p.set_defaults(fn=cmd_prune)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
