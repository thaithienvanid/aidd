#!/usr/bin/env bash
set -euo pipefail
# A repository that uses aidd with an approved Spec, SPEC-5, one Task whose scope is src/slug.py, and the failing test
# the Spec fixed. Approval covers code.edit inside that scope, so the run edits src/slug.py with no question.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
mkdir -p specs tests src
cat > specs/SPEC-5.md <<'MD'
---
aidd_version: "1.0.0"
type: spec
id: "SPEC-5"
title: "Slugs for article titles"
status: approved
approved_by: "@org/leads"
approved_at: "2026-11-02T09:00:00Z"
owner_team: "content"
change_type: "feat"
route: "normal"
confidence: high
open_questions: []
trace_id: "SPEC-5"
assisted_by: []
rollback: Revert the change.

risk:
  summary: "Article URLs use a slug of the title"
  dimensions: []
  reversible: true

tasks:
  - id: "SPEC-5-T1"
    title: "Write slugify"
    scope: ["src/slug.py"]

tests:
  files: ["tests/test_slug.py"]
  commands:
    - name: acceptance
      command: ["python3", "-m", "unittest", "tests.test_slug"]
      new_behavior: true
      covers: [A1]
---

## Intent

"Give each article a readable URL."

## Acceptance

- A1: given the title "Hello, World!", when slugify runs, then it returns "hello-world".
MD
printf 'def slugify(title):\n    raise NotImplementedError\n' > src/slug.py
printf 'import unittest\n\nfrom src.slug import slugify\n\n\nclass SlugTests(unittest.TestCase):\n    def test_title_becomes_a_slug(self):\n        self.assertEqual(slugify("Hello, World!"), "hello-world")\n\n\nif __name__ == "__main__":\n    unittest.main()\n' > tests/test_slug.py
git add -A && git commit -q -m "spec: SPEC-5 and its test"
git checkout -q -b feat/slugify
