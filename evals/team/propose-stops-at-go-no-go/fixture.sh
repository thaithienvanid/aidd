#!/usr/bin/env bash
set -euo pipefail
# An empty repository that uses aidd: the proposal starts from the request alone. The delivery manager creates the proposal
# inside the workspace, which the case lets it do. The files are ours and are written only inside the case's workspace.
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
git add -A
git commit -q -m "chore: start the repository"
