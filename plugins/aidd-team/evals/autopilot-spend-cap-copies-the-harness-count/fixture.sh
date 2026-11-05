#!/usr/bin/env bash
set -euo pipefail
# An approved Spec (SPEC-2) with one Task and its frozen test, in a small notes library that uses aidd, under a spend cap
# of 1,000 tokens (`agents.max_tokens_per_run`). Any role step passes that, so with the harness's count for each step
# autopilot stops after Implement to ask once; with no count, it says so once at launch and goes on. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd notes tests specs
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo

owners:
  approvers: ["@me"]

agents:
  max_tokens_per_run: 1000
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
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
cat > specs/SPEC-2.md <<'MD'
---
aidd_version: "1.0.0"
type: spec
id: SPEC-2
title: Limit the notes each user can keep
owner_team: app
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: SPEC-2
status: approved
approved_by: "@me"
approved_at: "2026-11-01T10:00:00Z"
assisted_by: []
rollback: Revert the change.
risk:
  summary: A user who holds 100 notes can no longer add another.
  dimensions: []
  reversible: true
tasks:
  - id: SPEC-2-T1
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
cat > tests/test_limit.py <<'PY'
import unittest

from notes.limit import NoteLimitReached, check_note_limit


class LimitTests(unittest.TestCase):
    def test_the_hundredth_note_is_allowed(self):
        self.assertIsNone(check_note_limit(99))

    def test_the_next_note_is_refused(self):
        with self.assertRaises(NoteLimitReached):
            check_note_limit(100)


if __name__ == "__main__":
    unittest.main()
PY
git add -A
git commit -q -m "test: freeze the SPEC-2 tests and approve the Spec"
