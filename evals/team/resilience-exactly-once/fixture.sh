#!/usr/bin/env bash
set -euo pipefail
# The prompt asks for work in a repository that uses aidd, so the workspace holds the minimal aidd config. Without it the aidd
# skill asks whether to apply aidd, and no practice skill loads. The file is ours and is written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
