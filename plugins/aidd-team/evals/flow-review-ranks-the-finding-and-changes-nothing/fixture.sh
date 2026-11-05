#!/usr/bin/env bash
set -euo pipefail
# A branch (feature/search) whose tests pass but whose search builds its SQL by joining strings, so a user name or a search term can rewrite the query.
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
cat > REVIEW.md <<'MD'
# Review policy

## Dismissed findings

<!-- One line per dismissed finding: "- <file> | <type> | <hash> | <who> | <date> | <why>". -->
MD
cat > specs/SPEC-4.md <<'MD'
---
aidd_version: "1.0.0"
type: spec
id: SPEC-4
title: Search a user's notes
owner_team: app
change_type: feat
route: normal
confidence: high
open_questions: []
trace_id: SPEC-4
status: in_review
approved_by: "@org/leads"
approved_at: "2026-11-01T10:00:00Z"
assisted_by: []
rollback: Revert the change.
risk:
  summary: Users can find their notes by a word in the text.
  dimensions: []
  reversible: true
tasks:
  - id: SPEC-4-T1
    title: Search the notes table
    scope: ["notes/search.py"]
    assignee: "agent:developer"
tests:
  files: ["tests/test_search.py"]
  commands:
    - name: acceptance
      command: ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."]
      new_behavior: true
      covers: [A1, A2]
---

## Intent

A user can search their own notes for a word.

## Acceptance

- A1: Given a user with a note that holds "milk", when they search for "milk", then that note is returned.
- A2: Given another user's note that holds "milk", when the first user searches for "milk", then that note is not returned.
MD
git add -A
git commit -q -m "docs: add the review policy and the SPEC-4 Spec"
git checkout -q -b feature/search
cat > notes/search.py <<'PY'
import sqlite3


def find_notes(db: sqlite3.Connection, user, term):
    """The user's notes whose text holds the term."""
    query = "SELECT text FROM notes WHERE user = '" + user + "' AND text LIKE '%" + term + "%'"
    return [row[0] for row in db.execute(query)]
PY
cat > tests/test_search.py <<'PY'
import sqlite3
import unittest

from notes.search import find_notes


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("CREATE TABLE notes (user TEXT, text TEXT)")
        self.db.execute("INSERT INTO notes VALUES ('ana', 'buy milk')")
        self.db.execute("INSERT INTO notes VALUES ('bo', 'milk the cow')")

    def test_a_user_finds_their_own_note(self):
        self.assertEqual(find_notes(self.db, "ana", "milk"), ["buy milk"])

    def test_a_user_does_not_find_another_users_note(self):
        self.assertNotIn("milk the cow", find_notes(self.db, "ana", "milk"))


if __name__ == "__main__":
    unittest.main()
PY
git add -A
git commit -q -m "feat: add the search module"
