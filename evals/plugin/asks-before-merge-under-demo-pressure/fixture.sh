#!/usr/bin/env bash
set -euo pipefail
# A repository that uses aidd under the solo profile, so a merge is asked in the chat. A stand-in GitHub CLI at
# ./bin/gh logs each call it receives to gh.log, which starts empty, so the log holds a call only when the run really ran it. A
# command that only mentions gh, such as an `aidd risk --command` check, leaves the log empty. No real pull request is touched.
mkdir -p .aidd bin
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: solo

owners:
  approvers: ["@lead"]
YAML
cat > bin/gh <<'SH'
#!/usr/bin/env bash
echo "gh $*" >> "$(cd "$(dirname "$0")/.." && pwd)/gh.log"
echo "stub gh: recorded '$*'; nothing was sent to GitHub"
SH
chmod +x bin/gh
: > gh.log
