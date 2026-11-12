#!/usr/bin/env bash
set -euo pipefail
# A small notes library in Python, in a repository that uses aidd under the solo profile. The store keeps notes in a list,
# and its one test passes. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd notes tests
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
: > notes/__init__.py
cat > notes/store.py <<'PY'
class Store:
    def __init__(self):
        self.notes = []

    def add(self, text):
        self.notes.append(text)
        return len(self.notes)
PY
cat > tests/test_store.py <<'PY'
from notes.store import Store


def test_add_counts_the_notes():
    assert Store().add("first") == 1
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: notes store"
