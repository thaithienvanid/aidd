#!/usr/bin/env bash
set -euo pipefail
# A repository that uses aidd with an agreed MVP plan (INTENT-1) for a terminal tool, so Day 0 runs: the architect's ADR and
# overview, no designer, and the SRE's scaffold. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd specs
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo

owners:
  approvers: ["@me"]
YAML
cat > BRIEF.md <<'MD'
# Brief

A command-line tool, in Python with the standard library only, that keeps a shared shopping list in a file: add an
item, tick it off, and list what is left. No screen beyond the terminal, no accounts, and no network.
MD
cat > specs/INTENT-1.md <<'MD'
---
aidd_version: "1.0.0"
type: intent
id: INTENT-1
title: A shared shopping list on the command line
goal: "Two people in one home keep one list for a week with no lost item"
owner_team: me
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
aidd_version: "1.0.0"
type: spec
id: SPEC-1
title: Add an item and show the list
owner_team: me
change_type: feat
route: normal
confidence: medium
open_questions: []
trace_id: SPEC-1
parent: INTENT-1
---

## Intent

"I add milk, and `list show` prints milk." (the slice in INTENT-1)
MD
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "docs: the agreed plan, INTENT-1, and the walking skeleton's draft Spec"
