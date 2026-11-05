#!/usr/bin/env bash
set -euo pipefail
# A built head for SPEC-3 whose tests pass but whose code breaks A2: a user with exactly 100 notes can still add one, because the check uses > and not >=.
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
cat > specs/SPEC-3.md <<'MD'
---
aidd_version: "1.0.0"
type: spec
id: SPEC-3
title: Limit the notes each user can keep
owner_team: app
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: SPEC-3
status: in_review
approved_by: "@org/leads"
approved_at: "2026-11-01T10:00:00Z"
assisted_by: []
rollback: Revert the change.
risk:
  summary: A user who holds 100 notes can no longer add another.
  dimensions: []
  reversible: true
tasks:
  - id: SPEC-3-T1
    title: Refuse a note once the limit is reached
    scope: ["notes/limit.py"]
    assignee: "agent:developer"
tests:
  files: ["tests/test_limit.py"]
  commands:
    - name: acceptance
      command: ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."]
      new_behavior: true
      covers: [A1, A2]
---

## Intent

A user can keep at most 100 notes. The next one is refused with a clear message.

## Acceptance

- A1: Given a user with 99 notes, when they add one, then it is accepted.
- A2: Given a user with 100 notes, when they add another, then it is refused with the message "You can keep at most 100 notes."
MD
git add -A
git commit -q -m "docs: add the SPEC-3 Spec"
git checkout -q -b feature/limit
cat > notes/limit.py <<'PY'
LIMIT = 100


class NoteLimitReached(Exception):
    """A user already holds as many notes as the limit allows."""


def check_note_limit(count):
    """Refuse a new note when the user already holds LIMIT notes."""
    if count > LIMIT:
        raise NoteLimitReached(f"You can keep at most {LIMIT} notes.")
PY
cat > tests/test_limit.py <<'PY'
import unittest

from notes.limit import NoteLimitReached, check_note_limit


class LimitTests(unittest.TestCase):
    def test_the_hundredth_note_is_allowed(self):
        self.assertIsNone(check_note_limit(99))

    def test_a_user_far_over_the_limit_is_refused(self):
        with self.assertRaises(NoteLimitReached):
            check_note_limit(150)


if __name__ == "__main__":
    unittest.main()
PY
git add -A
git commit -q -m "feat: refuse a note once the limit is reached"
