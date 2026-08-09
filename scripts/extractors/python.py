"""Extract the import graph and public surface of Python files using `ast`.

The extractor is deliberately split in two phases. `parse_file` works on one
file in isolation and yields unresolved import records; `Resolver` needs the
whole file set, because turning `from ..services import menu_cache` into
`src/app/services/menu_cache.py` is only decidable with the full tree in hand.
"""

from __future__ import annotations

import ast
import os
import posixpath
from dataclasses import dataclass, field


@dataclass
class RawImport:
    module: str | None
    names: list[str]
    level: int


@dataclass
class FileFacts:
    path: str
    imports: list[RawImport] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    parse_error: str | None = None


@dataclass
class Resolved:
    uses: list[str] = field(default_factory=list)
    external: list[str] = field(default_factory=list)


def parse_file(path: str, text: str) -> FileFacts:
    facts = FileFacts(path=path)
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        facts.parse_error = f"{exc.msg} (line {exc.lineno})"
        return facts

    dunder_all: list[str] | None = None
    defined: list[str] = []

    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                facts.imports.append(RawImport(module=alias.name, names=[], level=0))
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names if a.name != "*"]
            facts.imports.append(
                RawImport(module=node.module, names=names, level=node.level or 0)
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id == "__all__":
                        dunder_all = _string_list(node.value)
                    else:
                        defined.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined.append(node.target.id)

    # Nested imports still create a real dependency edge, so sweep the whole tree
    # for the ones the top-level pass missed.
    top_level = {id(n) for n in tree.body}
    for node in ast.walk(tree):
        if id(node) in top_level:
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                facts.imports.append(RawImport(module=alias.name, names=[], level=0))
        elif isinstance(node, ast.ImportFrom):
            names = [a.name for a in node.names if a.name != "*"]
            facts.imports.append(
                RawImport(module=node.module, names=names, level=node.level or 0)
            )

    if dunder_all is not None:
        facts.exports = dunder_all
    else:
        facts.exports = [n for n in defined if not n.startswith("_")]
    return facts


def _string_list(node: ast.AST) -> list[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple)):
        return None
    out = []
    for elt in node.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
    return out


class Resolver:
    """Maps dotted module names to repo-relative paths.

    Every file is registered under several aliases — one per plausible source
    root — because a repo may be imported as `app.routes.menu` (src layout),
    `src.app.routes.menu` (repo root on the path), or `routes.menu` (tests run
    from inside a package). Registering all of them and letting lookup pick the
    first hit is more robust than trying to divine the one true layout.
    """

    def __init__(self, paths: list[str]) -> None:
        self.paths = set(paths)
        self.index: dict[str, str] = {}
        self._dirs_with_init = {
            posixpath.dirname(p) for p in self.paths if posixpath.basename(p) == "__init__.py"
        }
        for path in sorted(paths):
            for alias in self._aliases(path):
                self.index.setdefault(alias, path)

    def _aliases(self, path: str) -> list[str]:
        if not path.endswith(".py"):
            return []
        stem = path[: -len(".py")]
        parts = stem.split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
            if not parts:
                return []

        aliases = [".".join(parts)]

        # Walk up while the enclosing directory is a package; the first
        # non-package ancestor is the source root, and the dotted name relative
        # to it is what user code will actually import.
        depth = 0
        cursor = posixpath.dirname(path)
        while cursor and cursor in self._dirs_with_init:
            depth += 1
            cursor = posixpath.dirname(cursor)
        if depth:
            trimmed = parts[len(parts) - depth - 1 :] if depth < len(parts) else parts
            aliases.append(".".join(trimmed))
        else:
            aliases.append(parts[-1])
        return [a for a in aliases if a]

    def _module_file(self, dotted: str) -> str | None:
        return self.index.get(dotted)

    def _path_candidates(self, base: str, module: str | None) -> list[str]:
        parts = [p for p in (module.split(".") if module else []) if p]
        target = posixpath.join(base, *parts) if parts else base
        return [f"{target}.py", posixpath.join(target, "__init__.py")]

    def resolve(self, facts: FileFacts) -> Resolved:
        uses: list[str] = []
        external: list[str] = []

        for imp in facts.imports:
            if imp.level:
                hits = self._resolve_relative(facts.path, imp)
                uses.extend(hits)
                continue
            hit = self._resolve_absolute(imp)
            if hit is None:
                if imp.module:
                    external.append(imp.module.split(".")[0])
            else:
                uses.extend(hit)

        uses = sorted({u for u in uses if u != facts.path})
        external = sorted(set(external))
        return Resolved(uses=uses, external=external)

    def _resolve_absolute(self, imp: RawImport) -> list[str] | None:
        if not imp.module:
            return None

        # `from a.b import c` is ambiguous: c may be a submodule or a symbol.
        # Submodule wins when it exists, which matches Python's own lookup.
        if imp.names:
            hits = []
            for name in imp.names:
                sub = self._module_file(f"{imp.module}.{name}")
                if sub:
                    hits.append(sub)
            own = self._module_file(imp.module)
            if own:
                hits.append(own)
            if hits:
                return sorted(set(hits))
            return None

        for candidate in _prefixes(imp.module):
            hit = self._module_file(candidate)
            if hit:
                return [hit]
        return None

    def _resolve_relative(self, importer: str, imp: RawImport) -> list[str]:
        base = posixpath.dirname(importer)
        for _ in range(imp.level - 1):
            base = posixpath.dirname(base)

        hits: list[str] = []
        for candidate in self._path_candidates(base, imp.module):
            if candidate in self.paths:
                hits.append(candidate)
                break

        parent = posixpath.join(base, *(imp.module.split(".") if imp.module else []))
        for name in imp.names:
            for candidate in (
                f"{posixpath.join(parent, name)}.py",
                posixpath.join(parent, name, "__init__.py"),
            ):
                if candidate in self.paths:
                    hits.append(candidate)
                    break
        return hits


def _prefixes(dotted: str) -> list[str]:
    parts = dotted.split(".")
    return [".".join(parts[: i + 1]) for i in range(len(parts))][::-1]


def is_test_path(path: str) -> bool:
    base = posixpath.basename(path)
    return (
        base.startswith("test_")
        or base.endswith("_test.py")
        or "tests/" in f"{posixpath.dirname(path)}/"
        or path.startswith("tests/")
    )


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def collect(paths: list[str], root: str = ".") -> tuple[dict[str, FileFacts], Resolver]:
    facts: dict[str, FileFacts] = {}
    for path in paths:
        full = os.path.join(root, path)
        try:
            facts[path] = parse_file(path, read_text(full))
        except OSError as exc:
            facts[path] = FileFacts(path=path, parse_error=str(exc))
    return facts, Resolver(list(facts))
