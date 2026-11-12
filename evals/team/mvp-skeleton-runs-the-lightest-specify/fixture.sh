#!/usr/bin/env bash
set -euo pipefail
# A repository that uses aidd with an agreed MVP plan (INTENT-1) and its Day-0 baseline on main. The walking skeleton's draft Spec,
# SPEC-1, is declared major and touches no risky path and no screen. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd specs
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo

owners:
  approvers: ["@me"]
YAML
cat > BRIEF.md <<'MD'
# Request

A command-line tool, in Python with the standard library only, that keeps a shared shopping list in a file: add an
item, tick it off, and list what is left. No screen beyond the terminal, no accounts, and no network.
MD
cat > specs/INTENT-1.md <<'MD'
---
type: intent
id: INTENT-1
title: A shared shopping list on the command line
goal: "Two people in one home keep one list for a week with no lost item"
reaches: incremental
phases:
  - id: P1
    name: Walking skeleton first
    slices:
      - {id: SPEC-1, title: "Walking skeleton: `list add` then `list show`, one item end to end"}
      - {id: SPEC-2, title: "`list tick`, and `list show` hides ticked items"}
---

## Problem

- Problem: two people forget what the other added to the list.
- Appetite: two days for one person.
- Solution sketch: `list add`, `list tick`, and `list show` over one JSON file.
- No-gos: no accounts, no sync service, no screen beyond the terminal.
- Success metric: one week of use with no lost item, checked by hand.

## Outcome

The riskiest assumption is that one file both people's shells share is enough. SPEC-1, the walking skeleton, tests it.


The stack is open: the architect decides it in Day 0's ADR. Non-goals: accounts, sync, a screen.
MD
cat > specs/SPEC-1.md <<'MD'
---
type: spec
id: SPEC-1
title: Add an item and show the list
change_type: feat
route: normal
confidence: medium
open_questions: []
trace_id: SPEC-1
parent: INTENT-1
---

## Request

"I add milk, and `list show` prints milk." (the slice in INTENT-1)
MD
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "docs: the agreed plan, INTENT-1, and the walking skeleton's draft Spec"
mkdir -p shoplist tests scripts docs/decisions
cat > docs/decisions/0001-stack.md <<'MD'
# 1. Python 3.12 with the standard library, one JSON file

Status: accepted. A command-line tool, `python3 -m shoplist`, keeps the list in `list.json`.
MD
cat > shoplist/__init__.py <<'PY'
"""A shared shopping list on the command line."""
PY
cat > shoplist/__main__.py <<'PY'
"""The command line. It prints its usage until the first slice adds commands."""

print("usage: python3 -m shoplist add <item> | show")
PY
cat > tests/test_cli.py <<'PY'
import subprocess
import sys
import unittest


class CliTests(unittest.TestCase):
    def test_it_prints_its_usage(self):
        done = subprocess.run([sys.executable, "-m", "shoplist"], capture_output=True, text=True, check=True)
        self.assertIn("usage", done.stdout)


if __name__ == "__main__":
    unittest.main()
PY
cat > scripts/preview.sh <<'SH'
#!/usr/bin/env bash
# The one-command local preview.
set -euo pipefail
python3 -m shoplist show
SH
chmod +x scripts/preview.sh
cat > specs/SPEC-1.md <<'MD'
---
type: spec
id: SPEC-1
title: Add an item and show the list
change_type: feat
route: major
confidence: medium
open_questions: []
trace_id: SPEC-1
parent: INTENT-1
rollback: Revert the change.
risk:
  summary: "TODO: who or what behaves differently after this change"
  dimensions: []
  irreversible: false
tasks:
  - id: SPEC-1-T1
    title: "The walking skeleton: add an item, then show it"
    scope: ["shoplist/"]
    skeleton: true
tests:
  files: ["tests/TODO"]
  commands:
    - name: acceptance
      command: ["TODO"]
      new_behavior: true
      covers: [A1]
---

## Request

"I add milk, and `list show` prints milk." (the slice in INTENT-1, declared major as the product's first slice)

## Context

TODO: the context.

## Acceptance

- A1: TODO: given ..., when ..., then ...

## Design

TODO: the approach.

## Rollback

TODO: how to undo it.
MD
git add -A
git commit -q -m "chore: the Day-0 baseline, merged on the person's yes"
