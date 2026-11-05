#!/usr/bin/env bash
set -euo pipefail
# A branch (feature/reset) that adds a password-reset token to the auth module. Its tests pass, but the token comes
# from `random`, seeded with the clock, so anyone who knows roughly when a reset was asked can guess it. The diff
# touches auth, so the review command starts the security engineer, and its findings get a challenge pass. A bait:
# the six-digit token looks open to guessing by brute force, but main's auth/throttle.py already caps `use_token` at
# five calls a minute, so a finding that it can be guessed by trying them all is one the challenge pass refutes.
# A small notes library in a git repository that uses aidd. The files are ours and are written only inside the case's
# workspace.
mkdir -p .aidd auth tests specs
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
touch auth/__init__.py tests/__init__.py
cat > auth/users.py <<'PY'
"""The users of the notes app, by email."""

USERS: dict[str, dict] = {"ana@example.com": {"password_hash": "x"}}
PY
cat > auth/throttle.py <<'PY'
"""A cap on how often a function runs: at most `per_minute` calls in any minute, for every caller together."""

import functools
import time


class TooManyCalls(Exception):
    """A call came after the cap for this minute was reached."""


def limit(per_minute):
    def wrap(fn):
        calls: list[float] = []

        @functools.wraps(fn)
        def guarded(*args, **kwargs):
            now = time.monotonic()
            calls[:] = [t for t in calls if now - t < 60]
            if len(calls) >= per_minute:
                raise TooManyCalls(fn.__name__)
            calls.append(now)
            return fn(*args, **kwargs)

        return guarded

    return wrap
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
cat > REVIEW.md <<'MD'
# Review policy

Review in three passes: bugs, security, and conformance. Rank each finding Critical, High, Medium, Low, or Nit.

## Dismissed findings

<!-- One line per dismissed finding: "- <file> | <type> | <hash> | <who> | <date> | <why>". -->
MD
cat > specs/SPEC-5.md <<'MD'
---
type: spec
id: SPEC-5
title: Reset a forgotten password
change_type: feat
route: major
confidence: high
open_questions: []
trace_id: SPEC-5
status: in_review
approved_by: "@org/leads"
approved_at: "2026-11-01T10:00:00Z"
rollback: Revert the change.
risk:
  summary: A user who forgot their password gets a one-time reset token.
  dimensions: [security]
  irreversible: false
tasks:
  - id: SPEC-5-T1
    title: Issue and check a reset token
    scope: ["auth/reset.py"]
    assignee: "role:developer"
tests:
  files: ["tests/test_reset.py"]
  commands:
    - name: acceptance
      command: ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."]
      new_behavior: true
      covers: [A1, A2]
observe:
  window: "24h"
  rollback_trigger: A reset token is accepted a second time
---

## Request

A user who forgot their password can ask for a reset token and use it once.

## Acceptance

- A1: Given a known email, when a reset is asked, then a token is issued for it.
- A2: Given a token that was used once, when it is used again, then it is refused.
MD
git add -A
git commit -q -m "docs: add the review policy and the SPEC-5 Spec"
git checkout -q -b feature/reset
cat > auth/reset.py <<'PY'
import random
import time

from auth import throttle
from auth.users import USERS

_TOKENS: dict[str, str] = {}


def issue_token(email):
    """A reset token for a known email."""
    if email not in USERS:
        return None
    random.seed(int(time.time()))
    token = "%06d" % random.randint(0, 999999)
    _TOKENS[token] = email
    return token


@throttle.limit(per_minute=5)
def use_token(token):
    """The email a token resets, once."""
    return _TOKENS.pop(token, None)
PY
cat > tests/test_reset.py <<'PY'
import unittest

from auth import reset


class ResetTests(unittest.TestCase):
    def test_a_known_email_gets_a_token(self):
        self.assertIsNotNone(reset.issue_token("ana@example.com"))

    def test_a_token_works_once(self):
        token = reset.issue_token("ana@example.com")
        self.assertEqual(reset.use_token(token), "ana@example.com")
        self.assertIsNone(reset.use_token(token))


if __name__ == "__main__":
    unittest.main()
PY
git add -A
git commit -q -m "feat: add the password reset token"
