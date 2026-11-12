#!/usr/bin/env bash
set -euo pipefail
# An API service whose one goal has two slices, and one slice sends health records: the case is the payment case's twin in another business domain. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
mkdir -p clinic
cat > clinic/api.py <<'PY'
"""The clinic API: appointments and lab results."""
PY
cat > BRIEF.md <<'MD'
# Request

The next release of `clinic`, an API service a clinic's staff call from their own tools.

Success criteria:
- `GET /appointments/today` lists today's appointments as plain text.
- A patient gets their lab results by email when a clinician releases them.

The service has no screen: other tools call its API.
MD
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "chore: start the repository"
