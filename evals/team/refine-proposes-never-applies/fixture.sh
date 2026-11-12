#!/usr/bin/env bash
set -euo pipefail
# A small backlog with one finding of each type refine looks for: an untriaged agent suggestion, two Specs that
# repeat each other, an Intent whose only slice is done, a Spec with no parent, and a Spec untouched for months.
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
    printf -- '---\ntype: spec\nid: %s\n' "$1"
    [ -n "$2" ] && printf 'parent: %s\n' "$2"
    printf -- 'title: "%s"\n%b---\n\n## Request\n\n%s\n' "$3" "$4" "$3"
  } > "specs/$1.md"
}
intent() { # id, title, the slices' ids
  {
    printf -- '---\ntype: intent\nid: %s\ntitle: "%s"\nphases:\n  - id: P1\n    name: "%s"\n    slices:\n' "$1" "$2" "$2"
    for s in $3; do printf '      - {id: %s, title: "%s"}\n' "$s" "$s"; done
    printf -- '---\n'
  } > "specs/$1.md"
}
intent INTENT-1 "Invoices" "SPEC-1 SPEC-2 SPEC-5"
intent INTENT-2 "Payment methods" "SPEC-3"
spec SPEC-1 INTENT-1 "Download an invoice as PDF" ""
spec SPEC-2 INTENT-1 "Export invoices to PDF" ""
spec SPEC-3 INTENT-2 "Save a card for later" 'status: done\n'
spec SPEC-4 "" "Show prices with tax" ""
spec SPEC-5 INTENT-1 "Email the invoice each month" 'suggested_by: role:product-manager\n'
git init -q
git -c user.name=fixture -c user.email=fixture@example.com add -A
GIT_AUTHOR_DATE=2026-05-04T10:00:00 GIT_COMMITTER_DATE=2026-05-04T10:00:00 \
  git -c user.name=fixture -c user.email=fixture@example.com commit -q -m "backlog"
