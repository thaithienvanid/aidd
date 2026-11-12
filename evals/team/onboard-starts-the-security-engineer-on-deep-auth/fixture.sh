#!/usr/bin/env bash
set -euo pipefail
# A service whose sign-in code sits four folders deep, past the depth `aidd init --dry-run` reads, and no aidd config.
# Onboarding starts the security engineer whenever the repository holds source code, so it finds the auth code the
# dry run misses. The files are ours and are written only inside the case's workspace.
mkdir -p services/api/app/auth
cat > services/api/app/auth/tokens.py <<'PY'
"""Issues and checks the sign-in tokens."""


def issue(user_id, secret):
    return f"{user_id}.{secret}"
PY
cat > README.md <<'MD'
# Service

The API service. Run the tests with `python3 -m unittest`.
MD
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A
git commit -q -m "chore: start the repository"
