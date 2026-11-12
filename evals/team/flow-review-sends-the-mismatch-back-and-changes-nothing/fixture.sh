#!/usr/bin/env bash
set -euo pipefail
# A built head for SPEC-3 whose tests pass but whose code breaks A2: a user with exactly 100 notes can still add one,
# because the check uses > and not >=.
# A small notes library in a git repository that uses aidd, with one passing test. The history is the loop's own order,
# so the review's findings are about the change and not the fixture: on main the library, then the ready Spec with its
# frozen tests, then the approval in its own commit with an Approved-by trailer, each on a pinned date. The branch
# feature/limit holds one Implement commit inside the Task's scope, with its Assisted-by trailer: the rule in
# notes/limit.py, its call in add_note, and the status in_review. The files are ours and are written only inside the
# case's workspace.
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

# The Spec, written three times: ready with its frozen tests, approved, and in review. Only the status lines differ.
# The Implement commit's Assisted-by trailer names the model, so the Spec lists none.
spec() {
  cat <<'MD'
---
type: spec
id: SPEC-3
title: Limit the notes each user can keep
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: SPEC-3
MD
  printf '%s\n' "$@"
  cat <<'MD'
rollback: Revert the change.
risk:
  summary: A user who holds 100 notes can no longer add another.
  dimensions: []
  irreversible: false
tasks:
  - id: SPEC-3-T1
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

The rule lives in notes/limit.py: LIMIT, the NoteLimitReached error, and check_note_limit, which raises it with the A2
message once a user holds LIMIT notes. add_note in notes/store.py runs the check before it adds the note.

## Acceptance

- A1: Given a user with 99 notes, when they add one, then it is accepted.
- A2: Given a user with 100 notes, when they add another, then it is refused with the message "You can keep at most 100 notes."
MD
}
APPROVED=("status: approved" 'approved_by: "@org/leads"' 'approved_at: "2026-11-01T10:00:00Z"')
spec "status: ready" > specs/SPEC-3.md
cat > tests/test_limit.py <<'PY'
import unittest

from notes import store
from notes.limit import NoteLimitReached, check_note_limit


class LimitTests(unittest.TestCase):
    def test_a_user_with_99_notes_can_add_one(self):
        for n in range(99):
            store.add_note("limit-a1", f"note {n}")
        store.add_note("limit-a1", "the hundredth")
        self.assertEqual(store.count_notes("limit-a1"), 100)

    def test_a_user_far_over_the_limit_is_refused(self):
        with self.assertRaises(NoteLimitReached):
            check_note_limit(150)


if __name__ == "__main__":
    unittest.main()
PY
git add -A
GIT_AUTHOR_DATE=2026-10-31T15:00:00Z GIT_COMMITTER_DATE=2026-10-31T15:00:00Z git commit -q -m "test: freeze the SPEC-3 acceptance tests, red on this commit"
spec "${APPROVED[@]}" > specs/SPEC-3.md
git add -A
GIT_AUTHOR_DATE=2026-11-01T10:00:00Z GIT_COMMITTER_DATE=2026-11-01T10:00:00Z \
  git commit -q -m "docs: approve SPEC-3" -m "Approved-by: @org/leads"
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
cat > notes/store.py <<'PY'
"""An in-memory store of notes, one list for each user."""

from notes.limit import check_note_limit

_NOTES: dict[str, list[str]] = {}


def add_note(user, text):
    check_note_limit(count_notes(user))
    _NOTES.setdefault(user, []).append(text)


def count_notes(user):
    return len(_NOTES.get(user, []))
PY
spec "status: in_review" "${APPROVED[@]:1}" > specs/SPEC-3.md
git add -A
GIT_AUTHOR_DATE=2026-11-02T11:00:00Z GIT_COMMITTER_DATE=2026-11-02T11:00:00Z \
  git commit -q -m "feat: refuse a note once the limit is reached" -m "Assisted-by: claude-code/claude-sonnet-5-5"
