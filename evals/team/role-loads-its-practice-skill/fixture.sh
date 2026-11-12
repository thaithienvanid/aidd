#!/usr/bin/env bash
set -euo pipefail
# The module the prompt names, with the pluralization bug in it, in a git repository that uses aidd (the prompt asks for
# a no-Spec fix). The files are ours and are written only inside the case's workspace.
mkdir -p .aidd
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
cat > stays.py <<'PY'
from datetime import date


def nights(check_in: date, check_out: date) -> int:
    return (check_out - check_in).days


def nights_label(check_in: date, check_out: date) -> str:
    n = nights(check_in, check_out)
    return f"{n} night" + ("s" if n > 2 else "")
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "feat: label the nights of a stay"
