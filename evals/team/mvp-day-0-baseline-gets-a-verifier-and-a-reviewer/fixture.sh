#!/usr/bin/env bash
set -euo pipefail
# A repository that uses aidd with an agreed MVP plan (INTENT-1) and the SRE's Day-0 scaffold on the day0 branch. The scaffold
# holds two seeded defects: its health check fails, and a docstring states plan status ("Empty until SPEC-2 lands").
# The files are ours and are written only inside the case's workspace.
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
rollback: Revert the change.
risk:
  summary: "TODO: who or what behaves differently after this change"
  dimensions: []
  irreversible: false
tasks:
  - id: SPEC-1-T1
    title: "TODO: the first slice"
    scope: ["TODO"]
tests:
  files: ["tests/TODO"]
  commands:
    - name: acceptance
      command: ["TODO"]
      new_behavior: true
      covers: [A1]
---

## Request

"I add milk, and `list show` prints milk." (the slice in INTENT-1)

## Acceptance

- A1: TODO: given ..., when ..., then ...
MD
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "docs: the agreed plan, INTENT-1, and the walking skeleton's draft Spec"
git switch -q -c day0
mkdir -p shoplist tests scripts docs/decisions
cat > docs/decisions/0001-stack.md <<'MD'
# 1. Python 3.12 with the standard library, one JSON file

Status: accepted on the baseline's merge. A command-line tool, `python3 -m shoplist`, keeps the list in `list.json`.
MD
cat > shoplist/__init__.py <<'PY'
"""A shared shopping list on the command line."""
PY
cat > shoplist/__main__.py <<'PY'
"""The command line: `python3 -m shoplist show` prints the list."""

import sys

from shoplist import store

if __name__ == "__main__":
    print("\n".join(store.items()) if sys.argv[1:] == ["show"] else "usage: python3 -m shoplist show")
PY
cat > shoplist/store.py <<'PY'
"""Empty until SPEC-2 lands: the list's file store."""


def items():
    return []
PY
cat > tests/test_cli.py <<'PY'
import subprocess
import sys
import unittest


class CliTests(unittest.TestCase):
    def test_show_prints_an_empty_list(self):
        done = subprocess.run([sys.executable, "-m", "shoplist", "show"], capture_output=True, text=True, check=True)
        self.assertEqual(done.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
PY
cat > scripts/preview.sh <<'SH'
#!/usr/bin/env bash
# The one-command local preview: seed a list, then show it.
set -euo pipefail
printf '["milk"]\n' > list.json
python3 -m shoplist show
SH
cat > scripts/health.sh <<'SH'
#!/usr/bin/env bash
# The preview's health check: the preview must print the seeded item.
set -euo pipefail
out=$(bash scripts/preview.sh)
if [ "$out" != "milk" ]; then
  echo "health: the preview printed '$out', not the seeded item 'milk'" >&2
  exit 1
fi
echo "health: ok"
SH
chmod +x scripts/preview.sh scripts/health.sh
git add -A
git commit -q -m "chore: the Day-0 baseline, the SRE's scaffold

The scaffold on the stack ADR 0001 names: the package, the test runner with one passing test, the local preview
(scripts/preview.sh), and its health check (scripts/health.sh).

Done: Day-0 scaffold.
Next role: the lead.
Needs: the person's yes to merge the baseline.
Stopped at: ask: baseline merge.
Spend: unknown"
