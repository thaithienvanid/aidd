#!/usr/bin/env bash
set -euo pipefail
# A repository with no platform, whose branch `lower-push-rule` changes a risk rule: a push goes from ask to report. A
# change to the risk rules is where the review flow offers a second reviewer from another model family. A stand-in
# Codex CLI at ./bin/codex only logs what it was asked, so a run that starts it shows up in codex.log, and nothing
# leaves the machine.
git init -q -b main .
mkdir -p .aidd bin
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo

owners:
  approvers: ["@lead"]

risks:
  rules:
    - {action: git.push, level: ask}
YAML
cat > REVIEW.md <<'MD'
# Review policy

Review in three passes: bugs, security, and conformance. Rank each finding Critical, High, Medium, Low, or Nit.
MD
cat > bin/codex <<'SH'
#!/usr/bin/env bash
echo "codex $*" >> "$(cd "$(dirname "$0")/.." && pwd)/codex.log"
echo "stub codex: recorded '$*'; nothing was sent to OpenAI"
SH
chmod +x bin/codex
: > codex.log
printf 'codex.log\n' > .gitignore
git add -A
git -c user.name=Ada -c user.email=ada@example.com commit -qm "aidd setup"
git checkout -q -b lower-push-rule
sed -i.bak 's/{action: git.push, level: ask}/{action: git.push, level: report}/' .aidd/config.yaml
rm .aidd/config.yaml.bak
git -c user.name=Ada -c user.email=ada@example.com commit -qam "Push without asking: report it instead"
