#!/usr/bin/env bash
set -euo pipefail
# A small backlog with one finding of each kind refine looks for: an untriaged agent suggestion, two Specs that
# repeat each other, an Epic whose only Spec is done, a Spec with no parent, and a Spec untouched for months.
# The Specs are thin drafts on purpose. They fail `aidd validate`, and this eval does not need them to pass.
mkdir -p .aidd specs
cat > .aidd/config.yaml <<'YAML'
aidd_version: "1.0.0"
profile: team

owners:
  approvers: ["@org/leads"]
YAML
spec() { # id, parent ("" for none), title, extra front-matter lines
  {
    printf -- '---\naidd_version: "1.0.0"\nkind: spec\nid: %s\n' "$1"
    [ -n "$2" ] && printf 'parent: %s\n' "$2"
    printf -- 'title: "%s"\n%b---\n\n## Intent\n\n%s\n' "$3" "$4" "$3"
  } > "specs/$1.md"
}
cat > specs/INIT-1.md <<'MD'
---
aidd_version: "1.0.0"
kind: initiative
id: INIT-1
title: Self-service billing
---
MD
for e in "EPIC-1:Invoices" "EPIC-2:Payment methods"; do
  printf -- '---\naidd_version: "1.0.0"\nkind: epic\nparent: INIT-1\nid: %s\ntitle: "%s"\n---\n' "${e%%:*}" "${e#*:}" > "specs/${e%%:*}.md"
done
spec SPEC-1 EPIC-1 "Download an invoice as PDF" ""
spec SPEC-2 EPIC-1 "Export invoices to PDF" ""
spec SPEC-3 EPIC-2 "Save a card for later" 'status: done\n'
spec SPEC-4 "" "Show prices with tax" ""
spec SPEC-5 EPIC-1 "Email the invoice each month" 'suggested_by: agent:product-manager\n'
git init -q
git -c user.name=fixture -c user.email=fixture@example.com add -A
GIT_AUTHOR_DATE=2026-05-04T10:00:00 GIT_COMMITTER_DATE=2026-05-04T10:00:00 \
  git -c user.name=fixture -c user.email=fixture@example.com commit -q -m "backlog"
