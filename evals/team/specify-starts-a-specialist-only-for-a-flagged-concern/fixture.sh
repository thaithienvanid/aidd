#!/usr/bin/env bash
set -euo pipefail
# A notes library in a repository that uses aidd, with a normal draft Spec (SPEC-1) that imports a note from a web
# address the user pastes. The server fetches that address, so the change holds one real security concern (a request
# to an internal address), and no personal data, compliance target, or AI feature. The files are ours and are written
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
type: spec
id: SPEC-1
title: Import a note from a web page
change_type: feat
route: normal
confidence: medium
open_questions: []
trace_id: SPEC-1
rollback: Revert the change.
risk:
  summary: "TODO: who or what behaves differently after this change"
  dimensions: [availability]
  irreversible: false
tasks:
  - id: SPEC-1-T1
    title: "TODO: the first part of the work"
    scope: ["notes/importer.py"]
tests:
  files: ["tests/TODO"]
  commands:
    - name: acceptance
      command: ["TODO"]
      new_behavior: true
      covers: [A1]
---

## Request

"A user pastes the address of a web page, and the page's text is saved as a new note." (the slice in the Intent)

## Context

Domain packs this change touches: `aidd-packs:apis-and-services`. The server fetches the page. The notes hold only what the user types or imports, and the project has no compliance target.

## Acceptance

- A1: TODO: given ..., when ..., then ...

## Design

TODO: the approach.

## Rollback

TODO: how to undo it.
MD
git add -A
git commit -q -m "chore: add the notes library and the SPEC-1 draft"
