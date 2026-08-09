"""End-to-end scoping tests against a throwaway monorepo.

These drive the real CLI rather than importing it, because the thing under test
is the interaction between cwd, git, and the mirror — none of which a unit test
of the path helpers would exercise.

The property that matters: **coverage is scoped, visibility is not.** Scoping
both is the obvious implementation and it silently downgrades a real
cross-package edge into a dead `External` string, which is worse than having no
scoping at all.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

CLI = os.path.join(os.path.dirname(__file__), "..", "scripts", "reminiscence.py")

SERVICE = """\
from .utils import helper
from shared.log import log


def run():
    return helper(), log
"""

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}\n    expected: {want}\n    actual:   {got}")


def contains(label: str, haystack: str, needle: str, present: bool = True) -> None:
    if (needle in haystack) != present:
        verb = "missing from" if present else "unexpectedly in"
        failures.append(f"{label}\n    {needle!r} {verb} output")


def run(root: str, cwd: str, *args: str) -> str:
    out = subprocess.run(
        [sys.executable, CLI, *args],
        cwd=cwd, capture_output=True, text=True,
    )
    if out.returncode not in (0, 1, 2):
        failures.append(f"CLI crashed: {' '.join(args)}\n{out.stderr}")
    return out.stdout


def build(root: str) -> None:
    for service in ("api", "billing"):
        base = os.path.join(root, "services", service, "src", "app")
        os.makedirs(base)
        open(os.path.join(base, "__init__.py"), "w").close()
        with open(os.path.join(base, "utils.py"), "w") as fh:
            fh.write("def helper():\n    return 1\n")
        with open(os.path.join(base, "main.py"), "w") as fh:
            fh.write(SERVICE)

    shared = os.path.join(root, "libs", "shared", "src", "shared")
    os.makedirs(shared)
    open(os.path.join(shared, "__init__.py"), "w").close()
    with open(os.path.join(shared, "log.py"), "w") as fh:
        fh.write('log = "logger"\n')

    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=root, check=True,
    )


def read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def main() -> int:
    root = tempfile.mkdtemp(prefix="reminiscence-scope-")
    try:
        build(root)
        api = os.path.join(root, "services", "api")

        # Scope follows the terminal: init from inside a package.
        run(root, api, "scaffold")
        run(root, api, "map")

        listed = run(root, api, "sources").split()
        check("coverage is scoped to the package", sorted(listed),
              ["src/app/__init__.py", "src/app/main.py", "src/app/utils.py"])

        mirror = os.path.join(api, ".reminiscence")
        check("mirror lives at the scope root", os.path.isdir(mirror), True)
        check("no stray mirror at repo root", os.path.isdir(os.path.join(root, ".reminiscence")), False)

        note = read(os.path.join(mirror, "src", "app", "main.py.md"))

        # The whole point: an import into an uncovered package must stay a real
        # traversable path, not decay into an External string.
        contains("cross-scope edge resolves to a path",
                 note, "- ../../libs/shared/src/shared/log.py")
        contains("cross-scope import did NOT fall through to External",
                 note, "shared", present=True)
        external = note.split("## External\n")[1].splitlines()[0]
        check("External is empty for a resolvable cross-scope import", external, "—")

        # Same-name modules in sibling packages must not collide.
        contains("relative import stays in its own package",
                 note, "- src/app/utils.py")
        contains("did not bleed into the sibling service",
                 note, "billing", present=False)

        # A second mirror, created from elsewhere via --scope.
        run(root, root, "scaffold", "--scope", "libs/shared")
        run(root, root, "map", "--scope", "libs/shared")
        log_note = read(os.path.join(
            root, "libs", "shared", ".reminiscence", "src", "shared", "log.py.md"))

        # Back-edges must cross scope boundaries, including to packages that
        # have no mirror at all — that is the monorepo breaking-change warning.
        contains("back-edge from a covered scope",
                 log_note, "- ../../services/api/src/app/main.py")
        contains("back-edge from a package with NO mirror",
                 log_note, "- ../../services/billing/src/app/main.py")

        scopes = run(root, root, "scopes").split()
        check("both mirrors discovered", sorted(scopes), ["libs/shared", "services/api"])

        # Idempotence still holds per scope.
        before = read(os.path.join(mirror, "src", "app", "main.py.md"))
        run(root, api, "map")
        check("map is idempotent under scoping",
              read(os.path.join(mirror, "src", "app", "main.py.md")), before)
    finally:
        shutil.rmtree(root, ignore_errors=True)

    if failures:
        print(f"FAIL ({len(failures)})\n")
        for failure in failures:
            print(f"  {failure}\n")
        return 1
    print("PASS - coverage scoped, visibility repo-wide, cross-scope edges intact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
