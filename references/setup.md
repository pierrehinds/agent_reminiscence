# Setup

The hooks are what make diffusion happen. Without them, coverage never grows on
its own and the model degrades to manual filling — so install them, not just the
scripts.

## 1. Place the skill

```bash
git clone <this repo> ~/.claude/skills/reminiscence
```

Or add it to a project as `.claude/skills/reminiscence/`. Everything is stdlib
Python 3 — no install step, no dependencies.

## 2. Initialise the target repo

```bash
cd /path/to/your/repo
python3 ~/.claude/skills/reminiscence/scripts/reminiscence.py scaffold
python3 ~/.claude/skills/reminiscence/scripts/reminiscence.py map
```

`scaffold` also appends the scratch files to `.gitignore`:

```
.reminiscence/.dirty
.reminiscence/.graph.json
.reminiscence/.stop_state
```

**Commit `.reminiscence/` itself.** The notes are the point — they should travel
with the repo and be reviewable in diffs.

## 3. Install the hooks

Add to `.claude/settings.json` in the target repo. Merge with any existing
`hooks` block rather than replacing it.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/skills/reminiscence/hooks/post_tool_use.py",
            "timeout": 10
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/skills/reminiscence/hooks/stop.py",
            "timeout": 60,
            "statusMessage": "reminiscence: re-mapping graph"
          }
        ]
      }
    ]
  }
}
```

Validate the shape landed correctly:

```bash
jq -e '.hooks.Stop[].hooks[] | select(.type=="command") | .command' .claude/settings.json
```

Exit 0 and your command printed means it parsed. Exit 5 means malformed JSON or
wrong nesting — and a broken `settings.json` silently disables *every* setting in
that file, so fix it before moving on.

If the hooks do not fire afterwards, the settings watcher only watches
directories that already had a settings file when the session started. Open
`/hooks` once, or restart the session.

### What each hook does

**PostToolUse** appends the edited path to `.reminiscence/.dirty`. No model, no
note rewriting, no output. It exits 0 on every failure path — a memory layer
that can break a session is worse than one that misses a file.

**Stop** runs in two stages. First it re-maps the graph for the dirty set, which
is free and silent. Only then, if prose is genuinely missing or stale, does it
return `{"decision": "block", "reason": ...}` with the specific file list.

Loop safety does not depend on any payload flag: the block condition *is* the
dirty set, and the agent's response (write prose, then `stamp`) clears it, so the
next Stop has nothing to say. `.stop_state` is the backstop for a
non-cooperating turn — the same file set never blocks twice in a row.

## 4. Gate commits

```bash
cat > .git/hooks/pre-commit <<'EOF'
#!/bin/sh
python3 ~/.claude/skills/reminiscence/scripts/reminiscence.py map
python3 ~/.claude/skills/reminiscence/scripts/reminiscence.py verify || {
  echo "reminiscence: notes are stale or missing — see above" >&2
  exit 1
}
EOF
chmod +x .git/hooks/pre-commit
```

`verify` exits non-zero on `MISSING`, `ORPHAN` or `PROSE-STALE`. It deliberately
does **not** fail on `UNFILLED` — partial prose is the expected steady state
under diffusion, and failing on it would force a bulk fill nobody asked for.

For CI, the same two lines plus `--lint` if you want slop detection enforced.

## 5. Scoping what gets notes

`.reminiscenceignore` at the repo root, `fnmatch` patterns, one per line:

```
tests/fixtures/*
migrations/*
*_generated.py
```

`sources` already respects `.gitignore` for free — it enumerates via
`git ls-files`, so `node_modules` and friends are never walked.

## Uninstall

Remove the hook entries and `rm -rf .reminiscence`. Nothing else in the repo is
touched — reminiscence never modifies source files.
