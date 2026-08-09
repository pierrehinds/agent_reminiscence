"""Assert the exact edge set the extractor produces for each fixture layout.

Exactness matters more than coverage here: a resolver that silently drops an
edge degrades traversal into search, and a resolver that invents one sends the
agent to a file that has nothing to do with the task.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from extractors import python as px  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

SRC_LAYOUT_USES = {
    "src/app/__init__.py": set(),
    "src/app/models/__init__.py": {"src/app/models/menu.py"},
    "src/app/models/menu.py": {"src/app/models/pricing.py"},
    "src/app/models/pricing.py": {"src/app/models/menu.py"},
    "src/app/routes/__init__.py": set(),
    "src/app/routes/v1/__init__.py": set(),
    "src/app/routes/v1/menu.py": {
        "src/app/models/__init__.py",
        "src/app/models/menu.py",
        "src/app/services/__init__.py",
        "src/app/services/menu_cache.py",
    },
    "src/app/services/__init__.py": set(),
    "src/app/services/menu_cache.py": {"src/app/models/menu.py"},
    "tests/test_menu.py": {"src/app/routes/v1/menu.py"},
}

SRC_LAYOUT_EXTERNAL = {
    "src/app/models/pricing.py": {"decimal"},
    "src/app/routes/v1/menu.py": {"requests"},
    "src/app/services/menu_cache.py": {"json"},
}

SRC_LAYOUT_EXPORTS = {
    "src/app/models/menu.py": ["Menu", "MenuItem"],
    "src/app/models/pricing.py": ["TAX_RATE", "price_of"],
    "src/app/services/menu_cache.py": ["MENU_TTL", "get", "invalidate"],
    "src/app/routes/v1/menu.py": ["get_menu"],
}

FLAT_USES = {
    "pkg/__init__.py": set(),
    "pkg/alpha.py": set(),
    "pkg/beta.py": {"pkg/alpha.py"},
    "script.py": {"pkg/beta.py"},
}

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}\n    expected: {want}\n    actual:   {got}")


def walk(root: str) -> list[str]:
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".py"):
                full = os.path.join(dirpath, name)
                out.append(os.path.relpath(full, root).replace(os.sep, "/"))
    return sorted(out)


def run_case(name: str, expected_uses: dict, expected_external=None, expected_exports=None):
    root = os.path.join(FIXTURES, name)
    paths = walk(root)
    check(f"[{name}] file set", set(paths), set(expected_uses))

    facts, resolver = px.collect(paths, root=root)
    resolved = {p: resolver.resolve(f) for p, f in facts.items()}

    for path, want in expected_uses.items():
        got = set(resolved[path].uses)
        check(f"[{name}] {path} uses", got, want)

    for path, res in resolved.items():
        for target in res.uses:
            if target not in set(paths):
                failures.append(f"[{name}] {path} -> {target} does not exist")

    # Inversion must be total: a graph where A->B does not imply B<-A would
    # leave "who calls this?" answerable only by search, which is the whole
    # thing the note is meant to replace.
    inverted: dict[str, set[str]] = {p: set() for p in paths}
    for path, res in resolved.items():
        for target in res.uses:
            inverted[target].add(path)
    for path, res in resolved.items():
        for target in res.uses:
            if path not in inverted[target]:
                failures.append(f"[{name}] inversion lost edge {path} -> {target}")

    if expected_external:
        for path, want in expected_external.items():
            check(f"[{name}] {path} external", set(resolved[path].external), want)

    if expected_exports:
        for path, want in expected_exports.items():
            check(f"[{name}] {path} exports", sorted(facts[path].exports), sorted(want))


def main() -> int:
    run_case("srclayout", SRC_LAYOUT_USES, SRC_LAYOUT_EXTERNAL, SRC_LAYOUT_EXPORTS)
    run_case("flat", FLAT_USES)

    if failures:
        print(f"FAIL ({len(failures)})\n")
        for failure in failures:
            print(f"  {failure}\n")
        return 1
    print("PASS - edge sets exact, inversion total, no dangling edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
