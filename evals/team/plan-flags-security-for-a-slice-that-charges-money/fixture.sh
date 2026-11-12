#!/usr/bin/env bash
set -euo pipefail
# A command-line tool whose one goal has two slices, and one slice charges money: the case checks the architect's card flags security, and only then the security engineer starts. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
mkdir -p notes
cat > notes/cli.py <<'PY'
"""The notes command line: add and list notes in a local file."""
PY
cat > BRIEF.md <<'MD'
# Request

The 1.0 release of `notes`, a command-line tool that keeps notes in a local file.

Success criteria:
- `notes export` writes every note to one JSON file.
- `notes upgrade` puts a user on the paid plan, which charges 3 EUR a month through the payment provider's API.

The tool has no screen: it runs in a terminal.
MD
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "chore: start the repository"
