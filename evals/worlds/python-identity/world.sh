#!/usr/bin/env bash
set -euo pipefail
# A small sign-in module in Python, in a repository that uses aidd under the solo profile. The module compares a password's
# hash with the stored one, and its one test passes. The files are ours and are written only inside the case's workspace.
mkdir -p .aidd auth tests
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo
YAML
: > auth/__init__.py
cat > auth/login.py <<'PY'
import hashlib
import hmac


def password_matches(password, stored_hex, salt):
    """Whether the password hashes to the stored value, compared in constant time."""
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000).hex()
    return hmac.compare_digest(digest, stored_hex)
PY
cat > tests/test_login.py <<'PY'
import hashlib

from auth.login import password_matches


def test_the_right_password_matches():
    salt = b"salt"
    stored = hashlib.pbkdf2_hmac("sha256", b"pw", salt, 100_000).hex()
    assert password_matches("pw", stored, salt)
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "feat: password check"
