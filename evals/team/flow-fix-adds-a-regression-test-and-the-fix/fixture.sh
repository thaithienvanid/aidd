#!/usr/bin/env bash
set -euo pipefail
# A one-line bug: average_length divides by one more than the number of notes.
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
cat > notes/summary.py <<'PY'
"""Numbers shown on the notes page."""


def average_length(notes):
    """The mean length of the notes' text, or 0 when there are none."""
    if not notes:
        return 0
    lengths = [len(n) for n in notes]
    return sum(lengths) / (len(lengths) + 1)
PY
git add -A
git commit -q -m "feat: add the average note length"
