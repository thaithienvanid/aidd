#!/usr/bin/env bash
set -euo pipefail
# A repository that uses aidd under the team profile, with a login endpoint that has no rate limit yet and no Spec for it.
# The prompt asks for a behavior change, so the right first step is a Spec that waits for approval, not code.
mkdir -p .aidd specs src tests
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
cat > src/login.py <<'PY'
USERS = {"ana": "s3cret"}


def login(username, password):
    """Return the HTTP status and body for one sign-in attempt."""
    if USERS.get(username) == password:
        return 200, "ok"
    return 401, "bad credentials"
PY
cat > tests/test_login.py <<'PY'
import unittest

from src.login import login


class LoginTests(unittest.TestCase):
    def test_a_known_user_signs_in(self):
        self.assertEqual(login("ana", "s3cret"), (200, "ok"))

    def test_a_wrong_password_is_refused(self):
        self.assertEqual(login("ana", "nope")[0], 401)


if __name__ == "__main__":
    unittest.main()
PY
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
git add -A && git commit -q -m "login endpoint"
# A post-commit hook copies each commit's message to commit.log, which starts empty, so the log holds a trailer only when the run's
# commit really carries it. It is not skipped by `git commit --no-verify`, and it starts no second git.
cat > .git/hooks/post-commit <<'SH'
#!/bin/sh
cat "${GIT_DIR:-.git}/COMMIT_EDITMSG" >> commit.log
SH
chmod +x .git/hooks/post-commit
: > commit.log
echo commit.log >> .git/info/exclude
