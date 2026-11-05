#!/usr/bin/env bash
set -euo pipefail
# A draft Spec (SPEC-1) in draft, with its intent quoted and every other section still a placeholder.
# A small notes library in a git repository that uses aidd, with one passing test. The files are ours and are written
# only inside the case's workspace.
mkdir -p .aidd notes tests specs
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
touch notes/__init__.py tests/__init__.py
cat > notes/store.py <<'PY'
"""An in-memory store of notes, one list for each user."""

_NOTES: dict[str, list[str]] = {}


def add_note(user, text):
    _NOTES.setdefault(user, []).append(text)


def count_notes(user):
    return len(_NOTES.get(user, []))
PY
cat > tests/test_store.py <<'PY'
import unittest

from notes import store


class StoreTests(unittest.TestCase):
    def test_a_new_user_has_no_notes(self):
        self.assertEqual(store.count_notes("ana"), 0)


if __name__ == "__main__":
    unittest.main()
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
cat > specs/SPEC-1.md <<'MD'
---
aidd_version: "1.0.0"
type: spec
id: SPEC-1
title: Limit the notes each user can keep
owner_team: app
change_type: feat
route: normal
confidence: medium
open_questions: []
trace_id: SPEC-1
assisted_by: []
rollback: Revert the change.
risk:
  summary: "TODO: who or what behaves differently after this change"
  dimensions: []
  reversible: true
tasks:
  - id: SPEC-1-T1
    title: "TODO: the first slice"
    scope: ["notes/TODO"]
tests:
  files: ["tests/TODO"]
  commands:
    - name: acceptance
      command: ["TODO"]
      new_behavior: true
      covers: [A1]
---

## Intent

"A user should be able to keep at most 100 notes. After that, adding another should be refused with a clear message." (the product manager's slice)

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
git commit -q -m "chore: add the notes library and the SPEC-1 draft"
