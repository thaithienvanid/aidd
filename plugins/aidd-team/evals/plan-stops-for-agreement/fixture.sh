#!/usr/bin/env bash
set -euo pipefail
# An empty repository that uses aidd: the plan starts from the request alone. The role subagents write the Intent
# inside the workspace, which the case lets them do. The files are ours and are written only inside the case's workspace.
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
