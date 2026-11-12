#!/usr/bin/env bash
set -euo pipefail
# The package.json the prompt shows, in a repository that uses aidd. The files are ours and are written only inside the
# case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
cat > package.json <<'JSON'
{
  "name": "shop-web",
  "version": "1.0.0",
  "dependencies": {
    "express": "4.18.2",
    "react": "18.2.0",
    "react-dom": "18.2.0",
    "left-pad": "1.3.0",
    "lodash": "4.17.20"
  },
  "devDependencies": {
    "eslint": "8.57.0",
    "jest": "29.7.0"
  }
}
JSON
