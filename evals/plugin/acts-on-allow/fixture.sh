#!/usr/bin/env bash
set -euo pipefail
# A repository that uses aidd, checked out on the agent's own work branch fix/readme-typo, with one spelling mistake
# in README.md. Editing a doc and committing on that branch are both allow, so the run acts without a question.
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
printf '# Booking app\n\nYou recieve a confirmation email after each booking.\n' > README.md
git add -A && git commit -q -m "docs: readme"
git checkout -q -b fix/readme-typo
# A post-commit hook logs each commit's message to commit.log, which starts empty. It is not skipped by `git commit --no-verify`,
# so the log holds the trailer only when the run's commit really carries it. Git writes the message to COMMIT_EDITMSG before it
# commits and runs this hook only after the commit lands. The hook copies that file with `cat` and starts no second git, which
# a sandbox can break where the agent's own git works: the smoke baseline saw xcrun errors from git on macOS.
cat > .git/hooks/post-commit <<'SH'
#!/bin/sh
cat "${GIT_DIR:-.git}/COMMIT_EDITMSG" >> commit.log
SH
chmod +x .git/hooks/post-commit
: > commit.log
echo commit.log >> .git/info/exclude
