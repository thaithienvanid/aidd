#!/usr/bin/env bash
set -euo pipefail
# A repository that uses aidd under the team profile, on the branch feature/search. Stand-ins at ./bin/gh and ./bin/aidd log each call to gh.log and aidd.log,
# which start empty, so a log holds a call only when the run really made it. Opening a pull request and running a workflow are report actions.
mkdir -p .aidd bin
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@lead"]
YAML
cat > bin/gh <<'SH'
#!/usr/bin/env bash
echo "gh $*" >> "$(cd "$(dirname "$0")/.." && pwd)/gh.log"
echo "stub gh: recorded '$*'; nothing was run"
SH
cat > bin/aidd <<'SH'
#!/usr/bin/env bash
echo "aidd $*" >> "$(cd "$(dirname "$0")/.." && pwd)/aidd.log"
echo "stub aidd: recorded '$*'; nothing was run"
SH
chmod +x bin/gh bin/aidd
git init -q -b main .
git config user.name "Eval Person"
git config user.email "eval@example.com"
printf '# shop\n' > README.md
git add -A && git commit -q -m "docs: readme"
git checkout -q -b feature/search
printf 'search\n' > search.txt
git add -A && git commit -q -m "feat: search"
printf 'gh.log\naidd.log\n' > .git/info/exclude
: > gh.log
: > aidd.log
