#!/usr/bin/env bash
set -euo pipefail
# A project with no source file yet, in a repository that uses aidd under the solo profile: a request in BRIEF.md and the
# config. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
printf '# Request\n\nA tool that lists what is due this week.\n' > BRIEF.md
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "docs: the request"
