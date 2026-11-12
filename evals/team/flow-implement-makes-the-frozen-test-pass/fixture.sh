#!/usr/bin/env bash
set -euo pipefail
# An approved Spec (SPEC-2) with one Task, and its frozen test, which fails because notes/limit.py does not exist yet.
# A small notes library in a git repository that uses aidd, with one passing test. The history is the loop's own order:
# the library, then the ready Spec with its frozen test, then the approval in its own commit with an Approved-by trailer,
# each on a pinned date before approved_at. The Task's scope holds the store too, so the Task can make add_note refuse
# the note, which the frozen test checks as a caller would. The files are ours and are written only inside the case's workspace.
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
git add -A
GIT_AUTHOR_DATE=2026-10-30T09:00:00Z GIT_COMMITTER_DATE=2026-10-30T09:00:00Z git commit -q -m "chore: start the notes library"

# The Spec, written twice: ready with its frozen test, then approved. Only the status lines differ.
spec() {
  cat <<'MD'
---
type: spec
id: SPEC-2
title: Limit the notes each user can keep
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: SPEC-2
MD
  printf '%s\n' "$@"
  cat <<'MD'
rollback: Revert the change.
risk:
  summary: A user who holds 100 notes can no longer add another.
  dimensions: []
  irreversible: false
tasks:
  - id: SPEC-2-T1
    title: Refuse a note once the limit is reached
    scope: ["notes/limit.py", "notes/store.py"]
    assignee: "role:developer"
tests:
  files: ["tests/test_limit.py"]
  commands:
    - name: acceptance
      command: ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."]
      new_behavior: true
      covers: [A1, A2]
---

## Request

A user can keep at most 100 notes. The next one is refused with a clear message.

## Context

The rule lives in notes/limit.py: LIMIT, the NoteLimitReached error, and a check that raises it with the A2 message once
a user holds LIMIT notes. add_note in notes/store.py runs the check before it adds the note, so every caller is refused.

## Acceptance

- A1: Given a user with 99 notes, when they add one, then it is accepted.
- A2: Given a user with 100 notes, when they add another, then it is refused with the message "You can keep at most 100 notes."
MD
}
spec "status: ready" > specs/SPEC-2.md
cat > tests/test_limit.py <<'PY'
import unittest

from notes import store
from notes.limit import NoteLimitReached


def fill(user, count):
    for n in range(count):
        store.add_note(user, f"note {n}")


class LimitTests(unittest.TestCase):
    def test_a_user_with_99_notes_can_add_one(self):
        fill("limit-a1", 99)
        store.add_note("limit-a1", "the hundredth")
        self.assertEqual(store.count_notes("limit-a1"), 100)

    def test_a_user_with_100_notes_is_refused_with_the_message(self):
        fill("limit-a2", 100)
        with self.assertRaises(NoteLimitReached) as refused:
            store.add_note("limit-a2", "one more")
        self.assertEqual(str(refused.exception), "You can keep at most 100 notes.")
        self.assertEqual(store.count_notes("limit-a2"), 100)


if __name__ == "__main__":
    unittest.main()
PY
git add -A
GIT_AUTHOR_DATE=2026-10-31T15:00:00Z GIT_COMMITTER_DATE=2026-10-31T15:00:00Z git commit -q -m "test: freeze the SPEC-2 acceptance tests, red on this commit"
spec "status: approved" 'approved_by: "@org/leads"' 'approved_at: "2026-11-01T10:00:00Z"' > specs/SPEC-2.md
git add -A
GIT_AUTHOR_DATE=2026-11-01T10:00:00Z GIT_COMMITTER_DATE=2026-11-01T10:00:00Z \
  git commit -q -m "docs: approve SPEC-2" -m "Approved-by: @org/leads"
