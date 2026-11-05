#!/usr/bin/env bash
set -euo pipefail
# An empty repository that uses aidd, with a short brief and no product code: autopilot's first matching path is the MVP,
# so it starts the product manager on the brief and asks no question about the path. The role subagents write the
# Intent inside the workspace, which the case lets them do. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo

owners:
  approvers: ["@me"]
YAML
cat > BRIEF.md <<'MD'
# Brief

Build a small web service that keeps a shared shopping list: add an item, tick it off, and list what is left.
MD
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "chore: start the repository"
